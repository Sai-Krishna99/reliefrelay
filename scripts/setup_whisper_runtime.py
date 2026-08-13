from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path


WHISPER_VERSION = "1.9.2"
OPTIMIZED_MODEL_NAME = "ggml-tiny.en-q5_1.bin"
OPTIMIZED_MODEL_URL = (
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"
    f"{OPTIMIZED_MODEL_NAME}?download=true"
)
OPTIMIZED_MODEL_SHA256 = (
    "c77c5766f1cef09b6b7d47f21b546cbddd4157886b3b5d6d4f709e91e66c7c2b"
)
BASELINE_MODEL_NAME = "ggml-tiny.en.bin"
BASELINE_MODEL_URL = (
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"
    f"{BASELINE_MODEL_NAME}?download=true"
)
BASELINE_MODEL_SHA256 = (
    "921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f"
)
GENERATED_MODEL_NAME = "ggml-tiny.en-q5_1-reliefrelay.bin"


@dataclass(frozen=True)
class RuntimeAsset:
    archive_name: str
    sha256: str
    download_url: str | None = None
    build_from_source: bool = False

    @property
    def url(self) -> str:
        if self.download_url:
            return self.download_url
        return (
            "https://github.com/ggml-org/whisper.cpp/releases/download/"
            f"v{WHISPER_VERSION}/{self.archive_name}"
        )


RUNTIME_ASSETS = {
    ("Windows", "AMD64"): RuntimeAsset(
        "whisper-bin-x64.zip",
        "49dcc16de826f20bd53d44f947a1ae49dfa81f86cad67a64d80820cb192d674a",
    ),
    ("Linux", "x86_64"): RuntimeAsset(
        "whisper-bin-ubuntu-x64.tar.gz",
        "46811a3ecf584307480a220b9ef5ff81b7b22dc41577cbc274ce3afc61f753b1",
    ),
    ("Linux", "aarch64"): RuntimeAsset(
        "whisper-bin-ubuntu-arm64.tar.gz",
        "7e26fa6a36d9174d5c0bf033ccbc026c3b5e569e2ee787058241346ef5392719",
    ),
    ("Darwin", "arm64"): RuntimeAsset(
        f"whisper.cpp-v{WHISPER_VERSION}.tar.gz",
        "a6abd064fcca8b85e794d205abf328c522e9451db43a3eadc178b883b7d0e9cd",
        download_url=(
            "https://github.com/ggml-org/whisper.cpp/archive/refs/tags/"
            f"v{WHISPER_VERSION}.tar.gz"
        ),
        build_from_source=True,
    ),
    ("Darwin", "x86_64"): RuntimeAsset(
        f"whisper.cpp-v{WHISPER_VERSION}.tar.gz",
        "a6abd064fcca8b85e794d205abf328c522e9451db43a3eadc178b883b7d0e9cd",
        download_url=(
            "https://github.com/ggml-org/whisper.cpp/archive/refs/tags/"
            f"v{WHISPER_VERSION}.tar.gz"
        ),
        build_from_source=True,
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, expected_sha256: str) -> None:
    print(f"Downloading {destination.name}")
    urllib.request.urlretrieve(url, destination)
    actual_sha256 = sha256(destination)
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            f"Checksum mismatch for {destination.name}: {actual_sha256}"
        )


def extract_archive(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zip_file:
            destination_root = destination.resolve()
            for member in zip_file.namelist():
                member_path = (destination / member).resolve()
                if destination_root not in member_path.parents:
                    raise RuntimeError(f"Unsafe archive path: {member}")
            zip_file.extractall(destination)
        return

    with tarfile.open(archive, "r:gz") as tar_file:
        tar_file.extractall(destination, filter="data")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Provision the Whisper.cpp runtime"
    )
    parser.add_argument(
        "--comparison",
        action="store_true",
        help="Download the full model and produce a Q5_1 model locally",
    )
    parser.add_argument("--metadata-output", type=Path)
    return parser.parse_args()


def find_executable(runtime_directory: Path, stem: str) -> Path:
    executable_name = f"{stem}.exe" if os.name == "nt" else stem
    executables = list(runtime_directory.rglob(executable_name))
    if len(executables) != 1:
        raise RuntimeError(f"Expected one {executable_name}, found {len(executables)}")
    if os.name != "nt":
        executables[0].chmod(executables[0].stat().st_mode | 0o111)
    return executables[0]


def ensure_model(path: Path, url: str, expected_sha256: str) -> None:
    if not path.exists() or sha256(path) != expected_sha256:
        download(url, path, expected_sha256)


def build_runtime_from_source(runtime_directory: Path) -> None:
    if shutil.which("cmake") is None:
        raise SystemExit(
            "CMake is required to build whisper.cpp on macOS. "
            "Install it with: brew install cmake"
        )
    source_directories = [
        path
        for path in runtime_directory.iterdir()
        if path.is_dir() and (path / "CMakeLists.txt").exists()
    ]
    if len(source_directories) != 1:
        raise RuntimeError(
            f"Expected one whisper.cpp source directory, found {len(source_directories)}"
        )
    source_directory = source_directories[0]
    build_directory = source_directory / "build-reliefrelay"
    subprocess.run(
        [
            "cmake",
            "-S",
            str(source_directory),
            "-B",
            str(build_directory),
            "-DCMAKE_BUILD_TYPE=Release",
            "-DWHISPER_BUILD_TESTS=OFF",
            "-DWHISPER_BUILD_EXAMPLES=ON",
        ],
        check=True,
    )
    subprocess.run(
        ["cmake", "--build", str(build_directory), "--parallel"],
        check=True,
    )


def quantize_model(
    quantizer_path: Path,
    baseline_path: Path,
    output_path: Path,
) -> dict[str, object]:
    output_path.unlink(missing_ok=True)
    started_at = time.perf_counter()
    subprocess.run(
        [str(quantizer_path), str(baseline_path), str(output_path), "q5_1"],
        check=True,
        capture_output=True,
        text=True,
    )
    duration_seconds = round(time.perf_counter() - started_at, 3)
    return {
        "quantization": "q5_1",
        "duration_seconds": duration_seconds,
        "baseline_model": baseline_path.name,
        "baseline_bytes": baseline_path.stat().st_size,
        "baseline_sha256": sha256(baseline_path),
        "optimized_model": output_path.name,
        "optimized_bytes": output_path.stat().st_size,
        "optimized_sha256": sha256(output_path),
    }


def setup(
    project_root: Path,
    *,
    comparison: bool = False,
    metadata_output: Path | None = None,
) -> None:
    platform_key = (platform.system(), platform.machine())
    asset = RUNTIME_ASSETS.get(platform_key)
    if asset is None:
        supported = ", ".join(
            f"{system}/{machine}" for system, machine in RUNTIME_ASSETS
        )
        raise SystemExit(f"Unsupported platform {platform_key}; supported: {supported}")

    runtime_directory = project_root / ".local" / "whisper"
    model_directory = project_root / "models" / "whisper"
    with tempfile.TemporaryDirectory(prefix="reliefrelay-whisper-") as directory:
        archive_path = Path(directory) / asset.archive_name
        download(asset.url, archive_path, asset.sha256)
        extract_archive(archive_path, runtime_directory)
    if asset.build_from_source:
        build_runtime_from_source(runtime_directory)

    model_directory.mkdir(parents=True, exist_ok=True)
    cli_path = find_executable(runtime_directory, "whisper-cli")

    if comparison:
        baseline_path = model_directory / BASELINE_MODEL_NAME
        optimized_path = model_directory / GENERATED_MODEL_NAME
        ensure_model(baseline_path, BASELINE_MODEL_URL, BASELINE_MODEL_SHA256)
        metadata = quantize_model(
            find_executable(runtime_directory, "whisper-quantize"),
            baseline_path,
            optimized_path,
        )
        metadata.update(
            {
                "whisper_cpp_version": WHISPER_VERSION,
                "architecture": platform.machine() or "unknown",
            }
        )
        if metadata_output:
            metadata_output.parent.mkdir(parents=True, exist_ok=True)
            metadata_output.write_text(
                json.dumps(metadata, indent=2) + "\n",
                encoding="utf-8",
            )
        print(f"Whisper baseline ready: {baseline_path}")
        print(f"ReliefRelay Q5_1 model ready: {optimized_path}")
    else:
        optimized_path = model_directory / OPTIMIZED_MODEL_NAME
        ensure_model(
            optimized_path,
            OPTIMIZED_MODEL_URL,
            OPTIMIZED_MODEL_SHA256,
        )
        print(f"Whisper model ready: {optimized_path}")

    print(f"Whisper runtime ready: {cli_path}")


if __name__ == "__main__":
    arguments = parse_args()
    setup(
        Path(__file__).resolve().parents[1],
        comparison=arguments.comparison,
        metadata_output=arguments.metadata_output,
    )
