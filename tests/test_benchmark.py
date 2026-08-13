from reliefrelay.benchmark import (
    build_comparison,
    percentile,
    render_comparison_markdown,
    render_github_notice,
    word_error_rate,
)


def test_word_error_rate_normalizes_case_and_punctuation() -> None:
    assert word_error_rate("Fire at North Clinic.", "fire at north clinic") == 0.0


def test_word_error_rate_counts_substitutions() -> None:
    assert word_error_rate("three people injured", "two people injured") == 0.3333


def test_percentile_uses_nearest_rank() -> None:
    assert percentile([0.9, 0.5, 0.7, 0.6, 0.8], 0.5) == 0.7
    assert percentile([0.9, 0.5, 0.7, 0.6, 0.8], 0.95) == 0.9


def test_comparison_reports_reductions_and_quality_guard() -> None:
    baseline = _report(
        model_bytes=100,
        model_mib=100.0,
        median_seconds=2.0,
        p95_seconds=3.0,
        real_time_factor=0.2,
        word_error_rate=0.1,
    )
    optimized = _report(
        model_bytes=40,
        model_mib=40.0,
        median_seconds=1.5,
        p95_seconds=2.0,
        real_time_factor=0.15,
        word_error_rate=0.11,
    )

    comparison = build_comparison(
        baseline,
        optimized,
        {
            "quantization": "q5_1",
            "baseline_sha256": "baseline-sha",
            "optimized_sha256": "optimized-sha",
        },
    )

    assert comparison["metrics"]["model_size_reduction_percent"] == 60.0
    assert comparison["metrics"]["median_latency_reduction_percent"] == 25.0
    assert comparison["quality_guard"]["passed"] is True
    assert "Quality guard: **PASS**" in render_comparison_markdown(comparison)
    assert render_github_notice(comparison) == (
        "Quality guard PASS; Q5_1 is 60.00% smaller; "
        "median latency reduction 25.00%; p95 latency reduction 33.33%; "
        "WER 11.00%; structured accuracy 100.00%"
    )

    invalid_provenance = build_comparison(
        baseline,
        optimized,
        {
            "quantization": "q5_1",
            "baseline_sha256": "wrong-sha",
            "optimized_sha256": "optimized-sha",
        },
    )
    assert invalid_provenance["quality_guard"]["passed"] is False

    poor_baseline = _report(
        model_bytes=100,
        model_mib=100.0,
        median_seconds=2.0,
        p95_seconds=3.0,
        real_time_factor=0.2,
        word_error_rate=0.4,
    )
    poor_optimized = _report(
        model_bytes=40,
        model_mib=40.0,
        median_seconds=1.5,
        p95_seconds=2.0,
        real_time_factor=0.15,
        word_error_rate=0.4,
    )
    assert build_comparison(
        poor_baseline,
        poor_optimized,
        {
            "baseline_sha256": "baseline-sha",
            "optimized_sha256": "optimized-sha",
        },
    )["quality_guard"]["passed"] is False


def _report(
    *,
    model_bytes: int,
    model_mib: float,
    median_seconds: float,
    p95_seconds: float,
    real_time_factor: float,
    word_error_rate: float,
) -> dict[str, object]:
    return {
        "runtime": {
            "architecture": "aarch64",
            "threads": 4,
            "runs": 5,
            "warmups": 1,
            "binary": "whisper-cli",
            "model_bytes": model_bytes,
            "model_mib": model_mib,
            "model_sha256": (
                "baseline-sha" if model_bytes == 100 else "optimized-sha"
            ),
        },
        "summary": {
            "fixture_count": 9,
            "sample_count": 45,
            "median_inference_seconds": median_seconds,
            "p95_inference_seconds": p95_seconds,
            "median_real_time_factor": real_time_factor,
            "mean_word_error_rate": word_error_rate,
            "structured_field_accuracy": 1.0,
        },
    }
