"""Versioned binary containers used by the XWASM final-stage package format.

The container layer is deliberately small and deterministic. It does not replace
WebAssembly; it packages standard WASM, PE32 payloads, resource archives, and
declarative API manifests behind explicit type tags.

v1 layout (little-endian):
    magic[6]       container signature
    version:u16    container format version
    kind:u8        container kind id
    compression:u8 0=stored, 1=zlib
    flags:u32      reserved; must be zero for v1
    raw_size:u64   uncompressed payload size
    data_size:u64  stored payload size
    sha256[32]     SHA-256 of the uncompressed payload
    data[...]      payload bytes

The format is intentionally not an executable format. In particular, .xapi
contains data only; bridge names are resolved against built-in runtime IDs.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

MAGIC = b"XWSC01"
VERSION = 1
_HEADER = struct.Struct("<6sHBBIQQ32s")

KIND_XWASM = 1
KIND_XPL = 2
KIND_XPAK = 3
KIND_XAPI = 4

KIND_NAMES = {
    KIND_XWASM: "xwasm",
    KIND_XPL: "xpl",
    KIND_XPAK: "xpak",
    KIND_XAPI: "xapi",
}
NAME_KINDS = {v: k for k, v in KIND_NAMES.items()}


@dataclass(frozen=True)
class ContainerInfo:
    kind: int
    version: int
    compression: int
    flags: int
    raw_size: int
    data_size: int
    sha256: str

    @property
    def kind_name(self) -> str:
        return KIND_NAMES.get(self.kind, f"unknown({self.kind})")


def _compress(data: bytes, compression: str) -> tuple[int, bytes]:
    if compression == "stored":
        return 0, data
    if compression == "zlib":
        return 1, zlib.compress(data, level=9)
    if compression == "auto":
        packed = zlib.compress(data, level=9)
        if len(packed) < len(data):
            return 1, packed
        return 0, data
    raise ValueError(f"unsupported compression: {compression!r}")


def pack_bytes(data: bytes, kind: int | str, *, compression: str = "auto") -> bytes:
    if isinstance(kind, str):
        try:
            kind = NAME_KINDS[kind.lower().lstrip(".")]
        except KeyError as exc:
            raise ValueError(f"unknown XWASM container kind: {kind!r}") from exc
    if kind not in KIND_NAMES:
        raise ValueError(f"unknown XWASM container kind id: {kind}")
    comp, stored = _compress(data, compression)
    digest = hashlib.sha256(data).digest()
    header = _HEADER.pack(MAGIC, VERSION, kind, comp, 0, len(data), len(stored), digest)
    return header + stored


def inspect_bytes(container: bytes) -> ContainerInfo:
    if len(container) < _HEADER.size:
        raise ValueError("container is truncated")
    magic, version, kind, compression, flags, raw_size, data_size, digest = _HEADER.unpack_from(container)
    if magic != MAGIC:
        raise ValueError("invalid XWASM container magic")
    if version != VERSION:
        raise ValueError(f"unsupported XWASM container version: {version}")
    if kind not in KIND_NAMES:
        raise ValueError(f"unknown XWASM container kind id: {kind}")
    if flags != 0:
        raise ValueError(f"unsupported XWASM container flags: 0x{flags:08x}")
    if compression not in (0, 1):
        raise ValueError(f"unsupported XWASM compression id: {compression}")
    if data_size != len(container) - _HEADER.size:
        raise ValueError("container data_size does not match file length")
    return ContainerInfo(kind, version, compression, flags, raw_size, data_size, digest.hex())


def unpack_bytes(container: bytes, *, expected_kind: int | str | None = None) -> tuple[ContainerInfo, bytes]:
    info = inspect_bytes(container)
    if expected_kind is not None:
        expected = NAME_KINDS[expected_kind.lower().lstrip(".")] if isinstance(expected_kind, str) else expected_kind
        if info.kind != expected:
            raise ValueError(f"expected {KIND_NAMES.get(expected, expected)!r}, got {info.kind_name!r}")
    stored = container[_HEADER.size:]
    data = zlib.decompress(stored) if info.compression == 1 else stored
    if len(data) != info.raw_size:
        raise ValueError("container raw_size does not match payload")
    if hashlib.sha256(data).hexdigest() != info.sha256:
        raise ValueError("container SHA-256 verification failed")
    return info, data


def pack_file(source: Path, destination: Path, kind: int | str, *, compression: str = "auto") -> ContainerInfo:
    data = source.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(pack_bytes(data, kind, compression=compression))
    return inspect_bytes(destination.read_bytes())


def unpack_file(source: Path, destination: Path, *, expected_kind: int | str | None = None) -> ContainerInfo:
    info, data = unpack_bytes(source.read_bytes(), expected_kind=expected_kind)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return info
