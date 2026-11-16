use std::hint::black_box;

use criterion::{BenchmarkId, Throughput};

use super::isize_pmf;
use crate::benchmark_support;

#[test]
#[ignore = "performance benchmark; run python3 benches/compare.py"]
fn benchmark_insert_size() {
    let mut criterion = benchmark_support::criterion();
    let mut group = criterion.benchmark_group("insert_size_pmf");
    group.throughput(Throughput::Elements(1));
    for (name, value, mean, sd) in [
        ("center", 312.0, 312.0, 12.0),
        ("off_center", 300.0, 312.0, 15.0),
        ("left_tail", 222.0, 312.0, 15.0),
        ("right_tail", 402.0, 312.0, 15.0),
        ("shifted", 350.0, 382.0, 40.0),
    ] {
        assert!(isize_pmf(value, mean, sd).is_valid());
        group.bench_function(name, |b| {
            b.iter(|| isize_pmf(black_box(value), black_box(mean), black_box(sd)))
        });
    }
    group.finish();

    // The sampling-bias calculation sweeps the mean +/- six standard deviations.
    let mut group = criterion.benchmark_group("insert_size_sweep");
    for sd in [15_u64, 40, 80] {
        let mean = 500_u64;
        let range = mean - 6 * sd..mean + 6 * sd;
        group.throughput(Throughput::Elements(range.end - range.start));
        group.bench_with_input(BenchmarkId::from_parameter(sd), &sd, |b, &sd| {
            b.iter(|| {
                for value in range.clone() {
                    black_box(isize_pmf(
                        black_box(value as f64),
                        black_box(mean as f64),
                        black_box(sd as f64),
                    ));
                }
            })
        });
    }
    group.finish();
    criterion.final_summary();
}
