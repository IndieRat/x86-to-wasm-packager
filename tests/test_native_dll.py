import struct
from pathlib import Path

import pytest

from xwasm.container import inspect_bytes, unpack_bytes
from xwasm.native_dll import inspect_native_dll, pack_native_dll


def synthetic_dll() -> bytes:
    # Minimal PE32 DLL with one section and no imports/relocations.
    data = bytearray(0x400)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 0x84, 0x14C, 1, 0, 0, 0, 224, 0x210E)
    oh = 0x98
    struct.pack_into("<H", data, oh, 0x10B)
    struct.pack_into("<I", data, oh + 16, 0x1000)
    struct.pack_into("<I", data, oh + 28, 0x10000000)
    struct.pack_into("<I", data, oh + 56, 0x2000)
    struct.pack_into("<I", data, oh + 60, 0x200)
    struct.pack_into("<I", data, oh + 92, 16)
    sh = oh + 224
    data[sh:sh + 8] = b".text\0\0\0"
    struct.pack_into("<IIIIIIHHI", data, sh + 8, 1, 0x1000, 0x200, 0x200, 0, 0, 0, 0, 0x60000020)
    data[0x200] = 0xC3
    return bytes(data)


def test_native_dll_inspection_and_xdll_roundtrip(tmp_path: Path):
    source = tmp_path / "sample.dll"
    output = tmp_path / "sample.xdll"
    source.write_bytes(synthetic_dll())

    manifest = inspect_native_dll(source)
    assert manifest["machine"] == "i386"
    assert manifest["pe32"] is True
    assert manifest["image_base"] == 0x10000000
    assert manifest["entry_rva"] == 0x1000
    assert manifest["size_of_image"] == 0x2000
    assert manifest["relocatable"] is False

    pack_native_dll(source, output)
    info = inspect_bytes(output.read_bytes())
    assert info.kind_name == "xdll"
    _, payload = unpack_bytes(output.read_bytes(), expected_kind="xdll")
    assert payload == source.read_bytes()


def test_native_dll_rejects_non_dll(tmp_path: Path):
    source = tmp_path / "program.exe"
    data = bytearray(synthetic_dll())
    struct.pack_into("<H", data, 0x96, 0x0002)
    source.write_bytes(data)
    with pytest.raises(ValueError, match="not marked IMAGE_FILE_DLL"):
        inspect_native_dll(source)
