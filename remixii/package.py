from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from .errors import PackageError
from .schema import validate_manifest

MAX_FILES = 32
MAX_FILE_SIZE = 150 * 1024 * 1024
MAX_TOTAL_SIZE = 350 * 1024 * 1024
# PCM silence is extremely compressible, so this remains deliberately high.
# Hard expanded-size limits above are the primary zip-bomb defense.
MAX_COMPRESSION_RATIO = 1000


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def media_record(path: str | Path, filename: str, duration: float) -> dict[str, Any]:
    return {
        "filename": filename,
        "duration_seconds": round(duration, 3),
        "sha256": sha256_file(path),
    }


def export_project(
    destination: str | Path,
    manifest: dict[str, Any],
    media_files: dict[str, str | Path],
) -> Path:
    errors = validate_manifest(manifest)
    if errors:
        raise PackageError("Cannot export invalid project: " + "; ".join(errors))
    target = Path(destination)
    if target.suffix.lower() != ".remix":
        target = target.with_suffix(".remix")
    target.parent.mkdir(parents=True, exist_ok=True)

    expected = {item["filename"] for item in manifest["media"].values()}
    if set(media_files) != expected:
        raise PackageError("Export media does not match the manifest.")

    temporary = target.with_name(target.name + ".tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8"),
            )
            for archive_name, source in media_files.items():
                path = Path(source)
                if not path.is_file() or sha256_file(path) != _expected_hash(manifest, archive_name):
                    raise PackageError(f"Media is missing or changed: {archive_name}")
                archive.write(path, archive_name)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def _expected_hash(manifest: dict[str, Any], filename: str) -> str:
    for item in manifest["media"].values():
        if item.get("filename") == filename:
            return item["sha256"]
    raise PackageError(f"Manifest does not declare {filename}")


def _validate_member(info: zipfile.ZipInfo) -> None:
    path = PurePosixPath(info.filename)
    if path.is_absolute() or ".." in path.parts or "\\" in info.filename or ":" in info.filename:
        raise PackageError(f"Unsafe archive path: {info.filename}")
    if info.flag_bits & 0x1:
        raise PackageError("Encrypted project entries are not supported.")
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise PackageError("Symbolic links are not allowed in projects.")
    if info.file_size > MAX_FILE_SIZE:
        raise PackageError(f"Project entry is too large: {info.filename}")
    if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
        raise PackageError(f"Suspicious compression ratio: {info.filename}")


def import_project(project_file: str | Path, destination: str | Path | None = None) -> tuple[dict[str, Any], Path]:
    source = Path(project_file)
    if not source.is_file():
        raise PackageError("The selected project file no longer exists.")
    if source.suffix.lower() != ".remix":
        raise PackageError("Select a .remix project file.")
    if destination is None:
        output = Path(tempfile.mkdtemp(prefix="remixii-open-"))
    else:
        output = Path(destination)
        if output.exists():
            raise PackageError("Import destination already exists; choose a new folder.")
        output.mkdir(parents=True)

    try:
        with zipfile.ZipFile(source, "r") as archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_FILES:
                raise PackageError("Project has an invalid number of entries.")
            total = 0
            seen: set[str] = set()
            for info in infos:
                _validate_member(info)
                if info.filename in seen:
                    raise PackageError(f"Duplicate project entry: {info.filename}")
                seen.add(info.filename)
                total += info.file_size
                if total > MAX_TOTAL_SIZE:
                    raise PackageError("Project expands beyond the allowed size.")
            if "manifest.json" not in seen:
                raise PackageError("Project is missing manifest.json.")
            try:
                manifest = json.loads(archive.read("manifest.json"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise PackageError("Project manifest is not valid UTF-8 JSON.") from exc
            errors = validate_manifest(manifest)
            if errors:
                raise PackageError("Invalid project manifest: " + "; ".join(errors))

            declared = {item["filename"]: item for item in manifest["media"].values()}
            if set(declared) - seen:
                raise PackageError("Project is missing declared media.")
            for name in declared:
                if not name.startswith("media/"):
                    raise PackageError("All declared media must be stored under media/.")

            archive.extractall(output)

        for name, item in declared.items():
            if sha256_file(output / Path(name)) != item["sha256"]:
                raise PackageError(f"Media hash mismatch: {name}")
        return manifest, output
    except zipfile.BadZipFile as exc:
        shutil.rmtree(output, ignore_errors=True)
        raise PackageError("The selected file is not a valid .remix archive.") from exc
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise
