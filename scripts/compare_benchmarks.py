from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from reliefrelay.benchmark import (
    build_comparison,
    render_comparison_markdown,
    render_github_notice,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare full-precision and quantized benchmark reports"
    )
    parser.add_argument("baseline", type=Path)
    parser.add_argument("optimized", type=Path)
    parser.add_argument("--quantization", required=True, type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    arguments = parse_args()
    comparison = build_comparison(
        read_json(arguments.baseline),
        read_json(arguments.optimized),
        read_json(arguments.quantization),
    )
    markdown = render_comparison_markdown(comparison)

    arguments.json_output.parent.mkdir(parents=True, exist_ok=True)
    arguments.json_output.write_text(
        json.dumps(comparison, indent=2) + "\n",
        encoding="utf-8",
    )
    arguments.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    arguments.markdown_output.write_text(markdown, encoding="utf-8")
    print(markdown, end="")

    if os.getenv("GITHUB_ACTIONS") == "true":
        title = "ReliefRelay native optimization result"
        notice = render_github_notice(comparison).replace("%", "%25")
        print(f"::notice title={title}::{notice}")

    if not comparison["quality_guard"]["passed"]:
        raise SystemExit("Optimized model failed the benchmark quality guard")
