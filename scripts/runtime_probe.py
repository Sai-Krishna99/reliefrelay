import argparse
import json
import os
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

from reliefrelay.platform_info import (
    default_inference_threads,
    processor_name,
    total_memory_bytes,
)


ARM64_NAMES = {"aarch64", "arm64"}


def collect_runtime() -> dict[str, str | bool | int | None]:
    architecture = platform.machine().lower()
    return {
        "architecture": architecture,
        "arm64": architecture in ARM64_NAMES,
        "operating_system": platform.system(),
        "operating_system_release": platform.release(),
        "processor": processor_name(),
        "logical_cpus": os.cpu_count(),
        "recommended_inference_threads": default_inference_threads(),
        "total_memory_bytes": total_memory_bytes(),
        "python": platform.python_version(),
        "captured_at": datetime.now(UTC).isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-arm64", action="store_true")
    arguments = parser.parse_args()

    runtime = collect_runtime()
    payload = json.dumps(runtime, indent=2)
    print(payload)

    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(payload + "\n", encoding="utf-8")

    if arguments.require_arm64 and not runtime["arm64"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
