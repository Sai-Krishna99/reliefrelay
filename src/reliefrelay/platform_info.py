from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path


def default_inference_threads() -> int:
    """Bound parallelism for small Arm systems while using larger client CPUs."""
    return max(1, min(6, os.cpu_count() or 4))


def processor_name() -> str:
    detected = platform.processor().strip()
    if platform.system() == "Darwin":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.stdout.strip():
                return result.stdout.strip()
        except (FileNotFoundError, subprocess.SubprocessError):
            pass
    if platform.system() == "Linux":
        try:
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
                key, _, value = line.partition(":")
                if key.strip().casefold() in {"model name", "hardware", "processor"}:
                    if value.strip():
                        return value.strip()
        except OSError:
            pass
    return detected or platform.machine() or "unknown"


def total_memory_bytes() -> int | None:
    if platform.system() == "Darwin":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            )
            return int(result.stdout.strip())
        except (FileNotFoundError, ValueError, subprocess.SubprocessError):
            return None
    if platform.system() == "Linux":
        try:
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            return None
    return None
