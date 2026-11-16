use std::hint::black_box;

use criterion::{BenchmarkId, Throughput};

use super::{AlleleFreq, Prior, PriorEstimate};
use crate::benchmark_support;

#[test]
#[ignore = "performance benchmark; run python3 benches/compare.py"]
fn benchmark_contamination_prior() {
    let mut criterion = benchmark_support::criterion();
    let mut group = criterion.benchmark_group("contamination_prior_grid");
    // Same candidate grid as Prior::as_json, including both probability endpoints.
    let candidates: Vec<_> = (0..=100).map(|i| AlleleFreq(i as f64 / 100.0)).collect();
    group.throughput(Throughput::Elements(candidates.len() as u64));
    for n_observed_cells in [10, 100, 1000] {
        let prior = Prior::new(Some(PriorEstimate {
            contamination: AlleleFreq(0.1),
            n_observed_cells,
        }));
        for &candidate in &candidates {
            assert!(prior.prob(candidate).is_valid());
        }
        group.bench_with_input(
            BenchmarkId::from_parameter(n_observed_cells),
            &prior,
            |b, prior| {
                b.iter(|| {
                    for &candidate in &candidates {
                        black_box(black_box(prior).prob(black_box(candidate)));
                    }
                })
            },
        );
    }
    group.finish();
    criterion.final_summary();
}
