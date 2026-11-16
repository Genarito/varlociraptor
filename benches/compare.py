#!/usr/bin/env python3
"""Compare identical Criterion workloads on a local Git ref and the working tree."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CRITERION = 'criterion = { version = "0.5", default-features = false, features = ["cargo_bench_support"] }'
HOOKS = {
    "src/lib.rs": '../benches/src/support.rs',
    "src/estimation/contamination.rs": '../../benches/src/contamination.rs',
    "src/variants/sampling_bias/fragments.rs": '../../../benches/src/fragments.rs',
}


def run(*command, **kwargs):
    print("+", " ".join(map(str, command)), flush=True)
    return subprocess.run(command, cwd=ROOT, check=True, **kwargs)


def install_harness(destination):
    """Overlay only benchmark code; keep the ref's production implementations."""
    bench_dir = destination / "benches" / "src"
    bench_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("support.rs", "contamination.rs", "fragments.rs"):
        shutil.copy2(ROOT / "benches" / "src" / filename, bench_dir / filename)
    manifest = destination / "Cargo.toml"
    source = manifest.read_text()
    if not any(line.startswith("criterion =") for line in source.splitlines()):
        source = source.replace("[dev-dependencies]", "[dev-dependencies]\n" + CRITERION, 1)
        manifest.write_text(source)
    for filename, relative in HOOKS.items():
        path = destination / filename
        source = path.read_text()
        if f'#[path = "{relative}"]' not in source:
            module = "benchmark_support" if filename == "src/lib.rs" else "benchmarks"
            source += f'\n#[cfg(test)]\n#[path = "{relative}"]\nmod {module};\n'
            path.write_text(source)
    # Seed both dependency resolutions identically, including untracked Cargo.lock.
    if (ROOT / "Cargo.lock").is_file():
        shutil.copy2(ROOT / "Cargo.lock", destination / "Cargo.lock")


def snapshots(base_commit, output):
    baseline = output / "source-master"
    baseline.mkdir()
    with tempfile.TemporaryFile() as archive:
        run("git", "archive", "--format=tar", base_commit, "--", "Cargo.toml", "src", "templates", stdout=archive)
        archive.seek(0)
        with tarfile.open(fileobj=archive) as contents:
            for member in contents.getmembers():
                target = (baseline / member.name).resolve()
                if not target.is_relative_to(baseline) or member.issym() or member.islnk():
                    raise RuntimeError(f"Unsafe archive entry: {member.name}")
            contents.extractall(baseline)
    current = output / "source-current"
    current.mkdir()
    for directory in ("src", "templates"):
        shutil.copytree(ROOT / directory, current / directory)
    shutil.copy2(ROOT / "Cargo.toml", current / "Cargo.toml")
    for snapshot in (baseline, current):
        install_harness(snapshot)
    return baseline, current


def build(source, output, label):
    result = run(
        "cargo", "test", "--release", "--lib", "--no-run",
        "--manifest-path", str(source / "Cargo.toml"),
        "--target-dir", str(ROOT / "target" / "benchmark-build"),
        "--message-format=json-render-diagnostics",
        stdout=subprocess.PIPE, text=True,
    )
    executables = [
        message["executable"]
        for message in map(json.loads, result.stdout.splitlines())
        if message.get("reason") == "compiler-artifact" and message.get("executable")
        and message.get("profile", {}).get("test")
    ]
    if len(executables) != 1:
        raise RuntimeError(f"Expected one library test executable, got {executables}")
    # Preserve it before building the other revision into the shared dependency cache.
    binary = output / (label + "-bench")
    shutil.copy2(executables[0], binary)
    return binary


def summarize(output):
    rows = []
    criterion = output / "criterion"
    for baseline in sorted(criterion.rglob("master/estimates.json")):
        current = baseline.parent.parent / "new" / "estimates.json"
        if not current.is_file():
            raise RuntimeError(f"Missing current measurement for {baseline.parent.parent}")
        old = json.loads(baseline.read_text())["mean"]["point_estimate"]
        new = json.loads(current.read_text())["mean"]["point_estimate"]
        rows.append({
            "benchmark": str(baseline.parent.parent.relative_to(criterion)),
            "master_mean_ns": old,
            "current_mean_ns": new,
            "change_percent": (new / old - 1) * 100,
            "speedup": old / new,
        })
    if not rows:
        raise RuntimeError("No benchmark results were produced")
    table = [
        "| Benchmark | Base mean (ns) | Current mean (ns) | Time change | Speedup |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        table.append(
            f'| {row["benchmark"]} | {row["master_mean_ns"]:.1f} | '
            f'{row["current_mean_ns"]:.1f} | {row["change_percent"]:+.2f}% | {row["speedup"]:.3f}x |'
        )
    report = "\n".join(table) + "\n"
    (output / "summary.md").write_text(report)
    (output / "summary.json").write_text(json.dumps(rows, indent=2) + "\n")
    print("\n" + report)
    print("Negative time change / speedup > 1 means faster. See Criterion output for significance.")
    print(f"Results and source snapshots: {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="master", help="local Git ref (default: master; never fetched)")
    parser.add_argument("--seconds", type=float, default=3, help="measurement seconds per workload (default: 3)")
    parser.add_argument("--samples", type=int, default=100, help="Criterion sample size, at least 10 (default: 100)")
    parser.add_argument("--quick", action="store_true", help="smoke check: 10 samples and 0.1 seconds per workload")
    args = parser.parse_args()
    if args.quick:
        args.seconds, args.samples = 0.1, 10
    if not 0 < args.seconds < float("inf") or args.samples < 10:
        parser.error("--seconds must be finite and positive; --samples must be at least 10")
    for command in ("git", "cargo", "rustc"):
        if shutil.which(command) is None:
            parser.error(f"{command} is required; run inside the project's build environment")
    commit = run("git", "rev-parse", "--verify", "--end-of-options", args.base + "^{commit}",
                 stdout=subprocess.PIPE, text=True).stdout.strip()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output = ROOT / "target" / "benchmarks" / f"{stamp}-{os.getpid()}"
    output.mkdir(parents=True)
    metadata = {
        "base_ref": args.base,
        "base_commit": commit,
        "current_head": run("git", "rev-parse", "HEAD", stdout=subprocess.PIPE, text=True).stdout.strip(),
        "working_tree_status": run("git", "status", "--porcelain", stdout=subprocess.PIPE, text=True).stdout,
        "rustc": run("rustc", "-Vv", stdout=subprocess.PIPE, text=True).stdout,
        "seconds": args.seconds,
        "samples": args.samples,
        "rustflags": os.environ.get("RUSTFLAGS", ""),
    }
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"Comparing {args.base} ({commit[:12]}) with the current working tree", flush=True)
    baseline, current = snapshots(commit, output)
    baseline_binary = build(baseline, output, "master")
    current_binary = build(current, output, "current")
    environment = os.environ.copy()
    environment.update({
        "VARLOCIRAPTOR_BENCH_OUTPUT": str(output / "criterion"),
        "VARLOCIRAPTOR_BENCH_SECONDS": str(args.seconds),
        "VARLOCIRAPTOR_BENCH_SAMPLES": str(args.samples),
    })
    for mode, binary in (("baseline", baseline_binary), ("compare", current_binary)):
        environment["VARLOCIRAPTOR_BENCH_MODE"] = mode
        run(str(binary), "benchmarks::benchmark_", "--ignored", "--nocapture", "--test-threads=1", env=environment)
    summarize(output)


if __name__ == "__main__":
    try:
        main()
    except (subprocess.CalledProcessError, RuntimeError, OSError) as error:
        sys.exit(f"Benchmark comparison failed: {error}")
