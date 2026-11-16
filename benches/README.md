# Comparing this branch with master

Run from the repository root on Linux, inside the usual Rust/native build environment:

```bash
pixi run python3 benches/compare.py --base master
```

`master` must already exist locally. The runner never fetches, switches branches,
stashes, stages, commits, or pushes. It compares that exact ref against the current
working tree, including staged, unstaged, and new source files. Both revisions are
copied into `target/benchmarks/<run>/` before building, so your checkout stays in
place and the measurements use consistent snapshots.

The master build still needs native GSL (`libgsl-dev` on Debian/Ubuntu). This
branch's Pixi manifest no longer lists GSL: either use a build environment that
already provides it, or install `libgsl-dev` alongside the project's usual native
dependencies before running. Python 3.9+ is required. The runner adds Criterion
only to the master snapshot; no benchmark code is substituted for production code.

For a quick compilation/execution smoke check, or longer measurements:

```bash
pixi run python3 benches/compare.py --quick
pixi run python3 benches/compare.py --base master --seconds 10 --samples 200
# A different already-fetched reference is also supported:
pixi run python3 benches/compare.py --base origin/master
```

The build time is excluded. Each workload warms up for one second, then collects
100 samples over approximately three seconds by default. Run with an otherwise
idle machine and the same CPU settings; repeat measurements before trusting small
changes. The quick mode is for validation, not performance conclusions.

## Workloads

- `insert_size_pmf`: the actual `isize_pmf` function at the center, away from the
  center, at both six-sigma tails, and with a shifted mean.
- `insert_size_sweep`: that function across the same +/- six-standard-deviation
  range used by fragment sampling bias, with three insert-size standard deviations.
- `contamination_prior_grid`: the actual `Prior::prob` over 101 candidate
  contamination fractions, including endpoints, for 10, 100, and 1000 cells.

These are Criterion microbenchmarks that call private production functions from
ignored unit tests. Ordinary `cargo test` skips them. We use the release profile,
serial execution, and `std::hint::black_box` to prevent constant folding. The runner
overlays the identical benchmark files and test-module declarations onto master.
Both builds start from the same current `Cargo.lock` when present, and keep their
resolved lockfiles with the snapshots. Unrelated dependencies therefore start from
the same versions; dependency changes required by each revision remain in effect.
Build dependencies are cached separately in `target/benchmark-build/`.

`src/calling/cnvs.rs` is disabled in both revisions (`calling/mod.rs` comments it
out), so it is intentionally outside this suite. These benchmarks isolate the
active numerical changes in this branch; they do not measure whole-pipeline I/O,
realignment, or variant-calling throughput. The existing benchmark CI workflow
covers preprocessing and calling with the larger repository fixtures.

## Reading results

Criterion prints time estimates, confidence intervals, and its statistical
comparison against the saved master baseline. A negative time change means faster;
a speedup greater than 1 means faster. A result within measurement noise should
not be treated as an improvement.

Every run keeps the following under `target/benchmarks/<run>/`:

- `summary.md` and `summary.json`: per-workload mean times and speedups.
- `criterion/`: master baselines, current samples, estimates, and comparisons.
- `metadata.json`: exact ref/commit, working-tree status, compiler, flags, settings.
- `source-master/`, `source-current/`, and compiled test executables.

The table compares mean times per iteration. For a sweep or grid, one iteration
means the entire sweep/grid; Criterion also reports element throughput. All output
is under the ignored `target/` directory. Nothing is pushed.
