from __future__ import annotations

import json
import struct
from pathlib import Path

I386 = 0x014C
IMAGE_FILE_DLL = 0x2000
SEED_DIR = Path(__file__).resolve().parents[1] / "runtime" / "x86" / "dlls"


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
    end = data.find(b"\0", off)
    if end < 0:
        end = len(data)
    return data[off:end].decode("ascii", "replace")


def pe_info(data: bytes) -> dict:
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError("input is not an MZ PE image")
    pe = _u32(data, 0x3C)
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("invalid PE signature")
    machine = _u16(data, pe + 4)
    sections = _u16(data, pe + 6)
    characteristics = _u16(data, pe + 22)
    optional_size = _u16(data, pe + 20)
    optional = pe + 24
    magic = _u16(data, optional)
    if machine != I386 or magic != 0x10B:
        raise ValueError(f"expected PE32/i386 DLL, machine=0x{machine:04X}, optional=0x{magic:04X}")
    if not (characteristics & IMAGE_FILE_DLL):
        raise ValueError("input is a PE32 executable, not a DLL")
    table = optional + optional_size
    section_rows = []
    for i in range(sections):
        off = table + i * 40
        name = data[off:off + 8].split(b"\0", 1)[0].decode("ascii", "replace")
        virtual_size = _u32(data, off + 8)
        virtual_address = _u32(data, off + 12)
        raw_size = _u32(data, off + 16)
        raw_pointer = _u32(data, off + 20)
        section_rows.append((name, virtual_address, max(virtual_size, raw_size), raw_pointer, raw_size))
    return {"pe_offset": pe, "optional": optional, "optional_size": optional_size, "sections": section_rows}


def rva_to_file(info: dict, rva: int) -> int:
    for _, va, size, raw, raw_size in info["sections"]:
        if va <= rva < va + size:
            delta = rva - va
            if delta >= raw_size:
                raise ValueError(f"RVA 0x{rva:X} has no file-backed bytes")
            return raw + delta
    raise ValueError(f"RVA 0x{rva:X} is outside PE sections")


def parse_exports(path: Path) -> list[str]:
    data = path.read_bytes()
    info = pe_info(data)
    optional = info["optional"]
    number_of_rva_sizes = _u32(data, optional + 92)
    if number_of_rva_sizes < 1:
        return []
    export_rva = _u32(data, optional + 96)
    export_size = _u32(data, optional + 100)
    if not export_rva:
        return []

    export_off = rva_to_file(info, export_rva)
    if export_off + 40 > len(data):
        raise ValueError("truncated export directory")
    number_of_names = _u32(data, export_off + 24)
    address_of_functions = _u32(data, export_off + 28)
    address_of_names = _u32(data, export_off + 32)
    address_of_name_ordinals = _u32(data, export_off + 36)

    names = []
    names_off = rva_to_file(info, address_of_names)
    ord_off = rva_to_file(info, address_of_name_ordinals)
    funcs_off = rva_to_file(info, address_of_functions)
    for i in range(number_of_names):
        name_rva = _u32(data, names_off + i * 4)
        ordinal_index = _u16(data, ord_off + i * 2)
        func_rva = _u32(data, funcs_off + ordinal_index * 4)
        name = _cstr(data, rva_to_file(info, name_rva))
        # An RVA inside the export directory is normally a forwarder string.
        forwarder = export_rva <= func_rva < export_rva + export_size
        names.append({"name": name, "ordinal_index": ordinal_index, "rva": func_rva, "forwarder": forwarder})
    return sorted(names, key=lambda x: x["name"].lower())


def load_seed(dll_name: str) -> dict:
    base = Path(dll_name).name.lower()
    seed = SEED_DIR / f"{Path(base).stem}.xapi"
    if not seed.is_file():
        raise FileNotFoundError(f"no XAPI seed exists for {dll_name!r}: {seed}")
    return json.loads(seed.read_text(encoding="utf-8"))


def convert_dll(path: Path, output: Path | None = None, *, strict: bool = False) -> tuple[dict, list[dict]]:
    exports = parse_exports(path)
    seed = load_seed(path.name)
    libraries = seed["libraries"]
    dll_key = next(iter(libraries))
    supported = libraries[dll_key]["functions"]

    exported_names = {item["name"] for item in exports}
    missing_from_dll = sorted(set(supported) - exported_names)
    unmapped = [item for item in exports if item["name"] not in supported]
    if strict and missing_from_dll:
        raise ValueError(f"{path.name}: seed exports missing from DLL: {', '.join(missing_from_dll)}")

    result = dict(seed)
    result["source"] = {
        "dll": path.name,
        "machine": "i386",
        "export_count": len(exports),
        "mapped_export_count": sum(1 for item in exports if item["name"] in supported),
        "unmapped_export_count": len(unmapped),
        "missing_seed_exports": missing_from_dll,
        "unmapped_exports": [item["name"] for item in unmapped],
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result, unmapped
