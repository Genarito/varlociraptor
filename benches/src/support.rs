//! Shared configuration for ignored Criterion benchmarks of private production code.

use std::{env, time::Duration};

use criterion::Criterion;

pub(crate) fn criterion() -> Criterion {
    let output = env::var_os("VARLOCIRAPTOR_BENCH_OUTPUT")
        .expect("run these benchmarks with python3 benches/compare.py");
    let seconds = env::var("VARLOCIRAPTOR_BENCH_SECONDS")
        .unwrap_or_else(|_| "3".to_owned())
        .parse::<f64>()
        .expect("VARLOCIRAPTOR_BENCH_SECONDS must be a number");
    let samples = env::var("VARLOCIRAPTOR_BENCH_SAMPLES")
        .unwrap_or_else(|_| "100".to_owned())
        .parse::<usize>()
        .expect("VARLOCIRAPTOR_BENCH_SAMPLES must be an integer");
    let criterion = Criterion::default()
        .without_plots()
        .output_directory(output.as_ref())
        .warm_up_time(Duration::from_secs(1))
        .measurement_time(Duration::from_secs_f64(seconds))
        .sample_size(samples);

    if env::var("VARLOCIRAPTOR_BENCH_MODE").as_deref() == Ok("baseline") {
        criterion.save_baseline("master".to_owned())
    } else {
        criterion.retain_baseline("master".to_owned(), true)
    }
}
