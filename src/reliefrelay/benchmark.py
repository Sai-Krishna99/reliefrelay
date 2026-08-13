import math
import re
from collections.abc import Sequence
from typing import Any


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def word_error_rate(reference: str, hypothesis: str) -> float:
    expected = _words(reference)
    actual = _words(hypothesis)
    previous = list(range(len(actual) + 1))
    for expected_index, expected_word in enumerate(expected, start=1):
        current = [expected_index]
        for actual_index, actual_word in enumerate(actual, start=1):
            substitution_cost = 0 if expected_word == actual_word else 1
            current.append(
                min(
                    previous[actual_index] + 1,
                    current[actual_index - 1] + 1,
                    previous[actual_index - 1] + substitution_cost,
                )
            )
        previous = current
    return round(previous[-1] / max(1, len(expected)), 4)


def percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("At least one value is required")
    if not 0 < quantile <= 1:
        raise ValueError("Quantile must be greater than 0 and at most 1")
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def _reduction_percent(baseline: float, optimized: float) -> float:
    if baseline == 0:
        return 0.0
    return round((baseline - optimized) / baseline * 100, 2)


def build_comparison(
    baseline: dict[str, Any],
    optimized: dict[str, Any],
    quantization: dict[str, Any],
    *,
    max_wer_regression: float = 0.02,
    max_optimized_wer: float = 0.20,
    min_structured_accuracy: float = 0.95,
    max_latency_regression: float = 0.05,
    max_p95_latency_regression: float = 0.10,
) -> dict[str, Any]:
    baseline_summary = baseline["summary"]
    optimized_summary = optimized["summary"]
    baseline_runtime = baseline["runtime"]
    optimized_runtime = optimized["runtime"]

    wer_delta = round(
        optimized_summary["mean_word_error_rate"]
        - baseline_summary["mean_word_error_rate"],
        4,
    )
    accuracy_delta = round(
        optimized_summary["structured_field_accuracy"]
        - baseline_summary["structured_field_accuracy"],
        4,
    )
    matching_environment = (
        baseline_runtime["architecture"] == optimized_runtime["architecture"]
        and baseline_runtime["threads"] == optimized_runtime["threads"]
        and baseline_runtime["runs"] == optimized_runtime["runs"]
        and baseline_runtime["warmups"] == optimized_runtime["warmups"]
        and baseline_runtime["binary"] == optimized_runtime["binary"]
        and baseline_summary["fixture_count"]
        == optimized_summary["fixture_count"]
        and baseline_summary["sample_count"]
        == optimized_summary["sample_count"]
    )
    quantization_matches = (
        quantization["baseline_sha256"] == baseline_runtime["model_sha256"]
        and quantization["optimized_sha256"] == optimized_runtime["model_sha256"]
    )
    baseline_fixtures = [item["file"] for item in baseline.get("fixtures", [])]
    optimized_fixtures = [item["file"] for item in optimized.get("fixtures", [])]
    matching_fixtures = (
        baseline_fixtures == optimized_fixtures
        if baseline_fixtures or optimized_fixtures
        else True
    )
    absolute_quality_passed = (
        optimized_summary["mean_word_error_rate"] <= max_optimized_wer
        and optimized_summary["structured_field_accuracy"]
        >= min_structured_accuracy
    )
    performance_within_limit = (
        optimized_summary["median_inference_seconds"]
        <= baseline_summary["median_inference_seconds"]
        * (1 + max_latency_regression)
        and optimized_runtime["model_bytes"] < baseline_runtime["model_bytes"]
        and optimized_summary["p95_inference_seconds"]
        <= baseline_summary["p95_inference_seconds"]
        * (1 + max_p95_latency_regression)
    )
    quality_preserved = (
        wer_delta <= max_wer_regression
        and accuracy_delta >= 0
        and matching_environment
        and quantization_matches
        and matching_fixtures
        and absolute_quality_passed
        and performance_within_limit
    )

    return {
        "benchmark": "ReliefRelay Whisper Tiny English optimization",
        "baseline": baseline_runtime,
        "optimized": optimized_runtime,
        "metrics": {
            "model_size_reduction_percent": _reduction_percent(
                baseline_runtime["model_bytes"], optimized_runtime["model_bytes"]
            ),
            "median_latency_reduction_percent": _reduction_percent(
                baseline_summary["median_inference_seconds"],
                optimized_summary["median_inference_seconds"],
            ),
            "p95_latency_reduction_percent": _reduction_percent(
                baseline_summary["p95_inference_seconds"],
                optimized_summary["p95_inference_seconds"],
            ),
            "median_real_time_factor_reduction_percent": _reduction_percent(
                baseline_summary["median_real_time_factor"],
                optimized_summary["median_real_time_factor"],
            ),
            "word_error_rate_delta": wer_delta,
            "structured_field_accuracy_delta": accuracy_delta,
        },
        "quality_guard": {
            "passed": quality_preserved,
            "matching_environment": matching_environment,
            "quantization_provenance_verified": quantization_matches,
            "matching_fixtures": matching_fixtures,
            "max_word_error_rate_regression": max_wer_regression,
            "max_optimized_word_error_rate": max_optimized_wer,
            "min_structured_field_accuracy": min_structured_accuracy,
            "max_latency_regression": max_latency_regression,
            "max_p95_latency_regression": max_p95_latency_regression,
            "word_error_rate_within_limit": wer_delta <= max_wer_regression,
            "structured_accuracy_preserved": accuracy_delta >= 0,
            "absolute_quality_passed": absolute_quality_passed,
            "performance_within_limit": performance_within_limit,
        },
        "summaries": {
            "baseline": baseline_summary,
            "optimized": optimized_summary,
        },
        "quantization": quantization,
    }


def render_comparison_markdown(comparison: dict[str, Any]) -> str:
    baseline = comparison["baseline"]
    optimized = comparison["optimized"]
    summaries = comparison["summaries"]
    baseline_summary = summaries["baseline"]
    optimized_summary = summaries["optimized"]
    metrics = comparison["metrics"]
    guard = comparison["quality_guard"]
    status = "PASS" if guard["passed"] else "FAIL"

    def latency_change(value: float) -> str:
        if value >= 0:
            return f"{value:.2f}% reduction"
        return f"{abs(value):.2f}% increase"

    return "\n".join(
        [
            f"## ReliefRelay {baseline['architecture']} optimization benchmark",
            "",
            f"Quality guard: **{status}**",
            "",
            "| Metric | Full precision | Q5_1 | Change |",
            "| --- | ---: | ---: | ---: |",
            (
                f"| Model size | {baseline['model_mib']:.2f} MiB | "
                f"{optimized['model_mib']:.2f} MiB | "
                f"{metrics['model_size_reduction_percent']:.2f}% smaller |"
            ),
            (
                f"| Median inference | "
                f"{baseline_summary['median_inference_seconds']:.3f} s | "
                f"{optimized_summary['median_inference_seconds']:.3f} s | "
                f"{latency_change(metrics['median_latency_reduction_percent'])} |"
            ),
            (
                f"| P95 inference | "
                f"{baseline_summary['p95_inference_seconds']:.3f} s | "
                f"{optimized_summary['p95_inference_seconds']:.3f} s | "
                f"{latency_change(metrics['p95_latency_reduction_percent'])} |"
            ),
            (
                f"| Median real-time factor | "
                f"{baseline_summary['median_real_time_factor']:.4f} | "
                f"{optimized_summary['median_real_time_factor']:.4f} | "
                f"{latency_change(metrics['median_real_time_factor_reduction_percent'])} |"
            ),
            (
                f"| Mean word error rate | "
                f"{baseline_summary['mean_word_error_rate']:.2%} | "
                f"{optimized_summary['mean_word_error_rate']:.2%} | "
                f"{metrics['word_error_rate_delta'] * 100:+.2f} pp |"
            ),
            (
                f"| Structured-field accuracy | "
                f"{baseline_summary['structured_field_accuracy']:.2%} | "
                f"{optimized_summary['structured_field_accuracy']:.2%} | "
                f"{metrics['structured_field_accuracy_delta'] * 100:+.2f} pp |"
            ),
            "",
            (
                f"Measured on {baseline.get('processor', 'unknown processor')} "
                f"(`{baseline['architecture']}`, "
                f"{baseline.get('operating_system', 'unknown OS')}) with "
                f"{baseline['threads']} threads, "
                f"{baseline_runtime_description(baseline_summary)}."
            ),
            (
                "The Q5_1 file was generated on the runner from the verified "
                "full-precision model."
            ),
            "",
        ]
    )


def baseline_runtime_description(summary: dict[str, Any]) -> str:
    return (
        f"{summary['fixture_count']} fixtures and "
        f"{summary['sample_count']} measured inferences"
    )


def render_github_notice(comparison: dict[str, Any]) -> str:
    metrics = comparison["metrics"]
    optimized_summary = comparison["summaries"]["optimized"]
    status = "PASS" if comparison["quality_guard"]["passed"] else "FAIL"
    return (
        f"Quality guard {status}; Q5_1 is "
        f"{metrics['model_size_reduction_percent']:.2f}% smaller; "
        f"median latency reduction "
        f"{metrics['median_latency_reduction_percent']:.2f}%; "
        f"p95 latency reduction "
        f"{metrics['p95_latency_reduction_percent']:.2f}%; "
        f"WER {optimized_summary['mean_word_error_rate']:.2%}; "
        f"structured accuracy "
        f"{optimized_summary['structured_field_accuracy']:.2%}"
    )
