from __future__ import annotations

import hashlib

import pytest

from xwasm.container import (
    KIND_XAPI,
    KIND_XPAK,
    KIND_XPL,
    KIND_XWASM,
    pack_bytes,
    unpack_bytes,
)


@pytest.mark.parametrize("kind", [KIND_XWASM, KIND_XPL, KIND_XPAK, KIND_XAPI])
@pytest.mark.parametrize("compression", ["stored", "zlib", "auto"])
def test_round_trip(kind: int, compression: str) -> None:
    payload = (b"XWASM final-stage container\0" * 97) + bytes(range(256))
    container = pack_bytes(payload, kind, compression=compression)
    info, unpacked = unpack_bytes(container, expected_kind=kind)
    assert unpacked == payload
    assert info.raw_size == len(payload)
    assert info.sha256 == hashlib.sha256(payload).hexdigest()


def test_kind_mismatch_rejected() -> None:
    container = pack_bytes(b"payload", KIND_XPL)
    with pytest.raises(ValueError, match="expected xapi"):
        unpack_bytes(container, expected_kind=KIND_XAPI)


def test_corrupt_payload_rejected() -> None:
    container = bytearray(pack_bytes(b"payload", KIND_XPL, compression="stored"))
    container[-1] ^= 0xFF
    with pytest.raises(ValueError, match="SHA-256"):
        unpack_bytes(bytes(container), expected_kind=KIND_XPL)
