"""Native PE32 DLL packaging for the XWASM guest-module loader.

This is deliberately different from XAPI.  XAPI describes host-implemented
compatibility APIs; an XDLL preserves a real PE32 DLL for execution by the
guest x86 CPU.  The converter validates the image and records loader metadata,
while the executable payload remains the original PE bytes.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

from .container import pack_bytes, inspect_bytes, unpack_bytes

I386 = 0x014C
IMAGE_FILE_DLL = 0x2000
IMAGE_FILE_RELOCS_STRIPPED = 0x0001


def _u16(data: bytes, off: int) -> int:
    if off < 0 or off + 2 > len(data):
        raise ValueError("truncated PE16 field")
    return struct.unpack_from("<H", data, off)[0]


def _u32(data: bytes, off: int) -> int:
    if off < 0 or off + 4 > len(data):
        raise ValueError("truncated PE32 field")
    return struct.unpack_from("<I", data, off)[0]


def _cstr(data: bytes, off: int) -> str:
    if off < 0 or off >= len(data):
        raise ValueError("invalid PE string offset")
    end = data.find(b"\\0", off)
    if end < 0:
        end = len(data)
    return data[off:end].decode("ascii", "replace")


def _rva_to_file(sections: list[dict], rva: int) -> int:
    for sec in sections:
        va = sec["virtual_address"]
        span = max(sec["virtual_size"], sec["raw_size"])
        if va <= rva < va + span:
            delta = rva - va
            if delta >= sec["raw_size"]:
                raise ValueError(f"RVA 0x{rva:X} is not file-backed")
            return sec["raw_pointer"] + delta
    raise ValueError(f"RVA 0x{rva:X} is outside PE sections")


def inspect_native_dll(path: Path) -> dict:
    data = path.read_bytes()
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError(f"{path.name}: not an MZ PE image")
    pe = _u32(data, 0x3C)
    if pe + 24 > len(data) or data[pe:pe + 4] != b"PE\0\0":
        raise ValueError(f"{path.name}: invalid PE signature")
    machine = _u16(data, pe + 4)
    sections_count = _u16(data, pe + 6)
    characteristics = _u16(data, pe + 22)
    optional_size = _u16(data, pe + 20)
    optional = pe + 24
    if machine != I386 or _u16(data, optional) != 0x10B:
        raise ValueError(f"{path.name}: expected PE32/i386 DLL")
    if not (characteristics & IMAGE_FILE_DLL):
        raise ValueError(f"{path.name}: image is not marked IMAGE_FILE_DLL")
    if optional + optional_size > len(data) or optional_size < 224:
        raise ValueError(f"{path.name}: truncated PE32 optional header")

    image_base = _u32(data, optional + 28)
    size_of_image = _u32(data, optional + 56)
    size_of_headers = _u32(data, optional + 60)
    entry_rva = _u32(data, optional + 16)
    directory_count = _u32(data, optional + 92)
    directories = []
    for i in range(min(directory_count, 16)):
        directories.append((_u32(data, optional + 96 + i * 8),
                            _u32(data, optional + 100 + i * 8)))
    while len(directories) < 16:
        directories.append((0, 0))

    section_table = optional + optional_size
    sections = []
    for i in range(sections_count):
        off = section_table + i * 40
        if off + 40 > len(data):
            raise ValueError(f"{path.name}: truncated section table")
        name = data[off:off + 8].split(b"\\0", 1)[0].decode("ascii", "replace")
        sections.append({
            "name": name,
            "virtual_size": _u32(data, off + 8),
            "virtual_address": _u32(data, off + 12),
            "raw_size": _u32(data, off + 16),
            "raw_pointer": _u32(data, off + 20),
            "characteristics": _u32(data, off + 36),
        })

    export_rva, export_size = directories[0]
    import_rva, import_size = directories[1]
    reloc_rva, reloc_size = directories[5]
    export_count = 0
    export_names = []
    dll_export_name = None
    if export_rva and export_size:
        eo = _rva_to_file(sections, export_rva)
        if eo + 40 > len(data):
            raise ValueError(f"{path.name}: truncated export directory")
        ordinal_base = _u32(data, eo + 16)
        function_count = _u32(data, eo + 20)
        name_count = _u32(data, eo + 24)
        functions_rva = _u32(data, eo + 28)
        names_rva = _u32(data, eo + 32)
        ordinals_rva = _u32(data, eo + 36)
        if _u32(data, eo + 12):
            try:
                dll_export_name = _cstr(data, _rva_to_file(sections, _u32(data, eo + 12)))
            except ValueError:
                dll_export_name = None
        export_count = function_count
        names_off = _rva_to_file(sections, names_rva) if name_count else 0
        ord_off = _rva_to_file(sections, ordinals_rva) if name_count else 0
        funcs_off = _rva_to_file(sections, functions_rva) if function_count else 0
        for i in range(min(name_count, 65536)):
            name_rva = _u32(data, names_off + i * 4)
            export_names.append(_cstr(data, _rva_to_file(sections, name_rva)))
        # Keep ordinal-base visible even when a DLL exports ordinal-only symbols.
        _ = ordinal_base, funcs_off, ord_off

    return {
        "format": "xwasm-native-dll",
        "version": 1,
        "dll": path.name,
        "machine": "i386",
        "pe32": True,
        "image_base": image_base,
        "size_of_image": size_of_image,
        "size_of_headers": size_of_headers,
        "entry_rva": entry_rva,
        "section_count": sections_count,
        "sections": sections,
        "import_rva": import_rva,
        "import_size": import_size,
        "reloc_rva": reloc_rva,
        "reloc_size": reloc_size,
        "relocatable": bool(reloc_rva and reloc_size and not (characteristics & IMAGE_FILE_RELOCS_STRIPPED)),
        "export_rva": export_rva,
        "export_size": export_size,
        "export_count": export_count,
        "export_names": sorted(set(export_names), key=str.lower),
        "export_module_name": dll_export_name,
        "sha256": __import__("hashlib").sha256(data).hexdigest(),
        "size": len(data),
    }


def convert_native_dll(path: Path, output: Path | None = None) -> dict:
    manifest = inspect_native_dll(path)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def pack_native_dll(path: Path, output: Path) -> dict:
    manifest = inspect_native_dll(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(pack_bytes(path.read_bytes(), "xdll", compression="auto"))
    inspect_bytes(output.read_bytes())
    _, payload = unpack_bytes(output.read_bytes(), expected_kind="xdll")
    if payload != path.read_bytes():
        raise ValueError(f"{path.name}: XDLL payload verification failed")
    return manifest
