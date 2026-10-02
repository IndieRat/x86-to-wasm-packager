from __future__ import annotations

from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile


class XWASMContainerError(ValueError):
    """Raised when a single-file XWASM container is invalid."""


def _member_name(path: Path, root: Path) -> str:
    relative = path.resolve().relative_to(root.resolve())
    name = PurePosixPath(relative.as_posix()).as_posix()
    if not name or name == ".":
        raise XWASMContainerError("cannot package the XWASM root itself")
    return name


def _validate_member_name(name: str) -> str:
    if not name or name.startswith("/") or "\\" in name:
        raise XWASMContainerError(f"unsafe XWASM member path: {name!r}")
    parts = PurePosixPath(name).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise XWASMContainerError(f"unsafe XWASM member path: {name!r}")
    return PurePosixPath(*parts).as_posix()


def pack_xwasm_directory(source: Path, output: Path) -> Path:
    source = source.resolve()
    output = output.resolve()

    if not source.is_dir():
        raise XWASMContainerError(f"XWASM source directory not found: {source}")
    if output.suffix.lower() != ".xwasm":
        raise XWASMContainerError("XWASM container output must use the .xwasm extension")
    if output.exists():
        raise XWASMContainerError(f"XWASM output already exists: {output}")

    manifest = source / "manifest.xwasm.json"
    if not manifest.is_file():
        raise XWASMContainerError("XWASM source is missing manifest.xwasm.json")

    output.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in source.rglob("*") if p.is_file())
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, _member_name(path, source))
    return output


def list_xwasm(path: Path) -> list[str]:
    path = path.resolve()
    if path.suffix.lower() != ".xwasm":
        raise XWASMContainerError("XWASM container must use the .xwasm extension")
    try:
        with ZipFile(path, "r") as archive:
            return [_validate_member_name(info.filename) for info in archive.infolist()]
    except BadZipFile as exc:
        raise XWASMContainerError(f"invalid XWASM container: {path}") from exc


def extract_xwasm(path: Path, output: Path) -> None:
    path = path.resolve()
    output = output.resolve()
    members = list_xwasm(path)

    with ZipFile(path, "r") as archive:
        for member in members:
            target = (output / member).resolve()
            try:
                target.relative_to(output)
            except ValueError as exc:
                raise XWASMContainerError(f"unsafe XWASM extraction path: {member!r}") from exc
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as src, target.open("wb") as dst:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
