from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from .format import XPAK_MANIFEST, make_xpak_manifest, validate_xpak_manifest


class XPAKError(ValueError):
    """Raised when an XPAK archive is invalid."""


def _archive_name(path: Path, root: Path) -> str:
    relative = path.resolve().relative_to(root.resolve())
    name = PurePosixPath(relative.as_posix()).as_posix()
    if not name or name == ".":
        raise XPAKError("cannot package the XPAK root itself")
    return name


def _validate_member_name(name: str) -> str:
    if not name or name.startswith("/") or "\\" in name:
        raise XPAKError(f"unsafe XPAK member path: {name!r}")
    parts = PurePosixPath(name).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise XPAKError(f"unsafe XPAK member path: {name!r}")
    return PurePosixPath(*parts).as_posix()


def make_xpak(source: Path, output: Path, name: str | None = None, kind: str = "data") -> Path:
    source = source.resolve()
    output = output.resolve()

    if not source.is_dir():
        raise XPAKError(f"XPAK source directory not found: {source}")
    if output.suffix.lower() != ".xpak":
        raise XPAKError("XPAK output must use the .xpak extension")
    if output.exists():
        raise XPAKError(f"XPAK output already exists: {output}")

    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = make_xpak_manifest(name or output.stem, kind=kind)

    files = sorted(p for p in source.rglob("*") if p.is_file())
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            XPAK_MANIFEST,
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )
        for path in files:
            archive.write(path, _archive_name(path, source))

    return output


def read_xpak_manifest(path: Path) -> dict:
    path = path.resolve()
    try:
        with ZipFile(path, "r") as archive:
            try:
                raw = archive.read(XPAK_MANIFEST)
            except KeyError as exc:
                raise XPAKError(f"missing {XPAK_MANIFEST}") from exc
    except BadZipFile as exc:
        raise XPAKError(f"invalid XPAK archive: {path}") from exc

    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise XPAKError(f"invalid XPAK manifest JSON: {exc}") from exc

    errors = validate_xpak_manifest(manifest)
    if errors:
        raise XPAKError("; ".join(errors))
    return manifest


def list_xpak(path: Path) -> list[str]:
    path = path.resolve()
    read_xpak_manifest(path)
    with ZipFile(path, "r") as archive:
        names = []
        for info in archive.infolist():
            if info.filename == XPAK_MANIFEST:
                continue
            names.append(_validate_member_name(info.filename))
        return names


def read_xpak_member(path: Path, member: str) -> bytes:
    path = path.resolve()
    member = _validate_member_name(member)
    read_xpak_manifest(path)
    try:
        with ZipFile(path, "r") as archive:
            return archive.read(member)
    except BadZipFile as exc:
        raise XPAKError(f"invalid XPAK archive: {path}") from exc
    except KeyError as exc:
        raise XPAKError(f"XPAK member not found: {member!r}") from exc


def extract_xpak(path: Path, output: Path) -> None:
    path = path.resolve()
    output = output.resolve()
    read_xpak_manifest(path)

    with ZipFile(path, "r") as archive:
        members = [_validate_member_name(info.filename) for info in archive.infolist() if info.filename != XPAK_MANIFEST]
        for member in members:
            target = (output / member).resolve()
            try:
                target.relative_to(output)
            except ValueError as exc:
                raise XPAKError(f"unsafe XPAK extraction path: {member!r}") from exc

            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as src, target.open("wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
