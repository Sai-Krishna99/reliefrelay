from __future__ import annotations

import hashlib
import os
import platform
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path


WHISPER_VERSION = "1.9.2"
MODEL_NAME = "ggml-tiny.en-q5_1.bin"
MODEL_URL = (
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"
    f"{MODEL_NAME}?download=true"
)
MODEL_SHA256 = "c77c5766f1cef09b6b7d47f21b546cbddd4157886b3b5d6d4f709e91e66c7c2b"


@dataclass(frozen=True)
class RuntimeAsset:
    archive_name: str
    sha256: str

    @property
    def url(self) -> str:
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


def setup(project_root: Path) -> None:
    platform_key = (platform.system(), platform.machine())
    asset = RUNTIME_ASSETS.get(platform_key)
    if asset is None:
        supported = ", ".join(f"{system}/{machine}" for system, machine in RUNTIME_ASSETS)
        raise SystemExit(f"Unsupported platform {platform_key}; supported: {supported}")

    runtime_directory = project_root / ".local" / "whisper"
    model_directory = project_root / "models" / "whisper"
    with tempfile.TemporaryDirectory(prefix="reliefrelay-whisper-") as directory:
        archive_path = Path(directory) / asset.archive_name
        download(asset.url, archive_path, asset.sha256)
        extract_archive(archive_path, runtime_directory)

    model_directory.mkdir(parents=True, exist_ok=True)
    model_path = model_directory / MODEL_NAME
    if not model_path.exists() or sha256(model_path) != MODEL_SHA256:
        download(MODEL_URL, model_path, MODEL_SHA256)

    executable_name = "whisper-cli.exe" if os.name == "nt" else "whisper-cli"
    executables = list(runtime_directory.rglob(executable_name))
    if len(executables) != 1:
        raise RuntimeError(f"Expected one {executable_name}, found {len(executables)}")
    if os.name != "nt":
        executables[0].chmod(executables[0].stat().st_mode | 0o111)
    print(f"Whisper runtime ready: {executables[0]}")
    print(f"Whisper model ready: {model_path}")


if __name__ == "__main__":
    setup(Path(__file__).resolve().parents[1])
