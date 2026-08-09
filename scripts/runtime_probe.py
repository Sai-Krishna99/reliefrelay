import argparse
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path


ARM64_NAMES = {"aarch64", "arm64"}


def collect_runtime() -> dict[str, str | bool]:
    architecture = platform.machine().lower()
    return {
        "architecture": architecture,
        "arm64": architecture in ARM64_NAMES,
        "operating_system": platform.system(),
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
