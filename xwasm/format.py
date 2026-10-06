from __future__ import annotations

import json
from pathlib import Path

FORMAT = "xwasm-package"
FORMAT_VERSION = 1
ABI = "xwasm.host/1"
META_SECTION = "xwasm.meta"


def make_manifest(name: str, module: str = "game.wasm", resource_root: str = "resources/") -> dict:
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "name": name,
        "architecture": "wasm32",
        "module": module,
        "bridge": None,
        "resource_root": resource_root,
        "abi": ABI,
        "entry": {"init": "xwasm_init", "tick": "xwasm_tick", "shutdown": "xwasm_shutdown"},
    }


def validate_manifest(manifest: dict) -> list[str]:
    errors = []
    if not isinstance(manifest, dict):
        return ["manifest is not an object"]
    if manifest.get("format") != FORMAT:
        errors.append(f"format must be {FORMAT!r}")
    if manifest.get("format_version") != FORMAT_VERSION:
        errors.append(f"unsupported format_version: {manifest.get('format_version')!r}")
    if not isinstance(manifest.get("name"), str) or not manifest["name"]:
        errors.append("name must be a non-empty string")

    architecture = manifest.get("architecture")
    if architecture not in {"wasm32", "x86", "x86-recompiled"}:
        errors.append("architecture must be 'wasm32', 'x86', or 'x86-recompiled'")

    if architecture in {"wasm32", "x86-recompiled"}:
        if not isinstance(manifest.get("module"), str) or not manifest["module"]:
            errors.append("module must be a non-empty string for wasm32/x86-recompiled packages")
    elif architecture == "x86":
        payload = manifest.get("payload")
        if not isinstance(payload, str) or not payload:
            errors.append("payload must be a non-empty string for x86 packages")
        if manifest.get("payload_format") not in {None, "PE32"}:
            errors.append("x86 payload_format must be PE32 or null")
        if manifest.get("payload_architecture") not in {None, "i386"}:
            errors.append("x86 payload_architecture must be i386 or null")

        runtime = manifest.get("runtime")
        if runtime is not None and not isinstance(runtime, str):
            errors.append("runtime must be a string or null for x86 packages")

    if not isinstance(manifest.get("resource_root"), str):
        errors.append("resource_root must be a string")
    if manifest.get("abi") != ABI:
        errors.append(f"unsupported abi: {manifest.get('abi')!r}")
    entry = manifest.get("entry")
    if not isinstance(entry, dict):
        errors.append("entry must be an object")
    else:
        for key in ("init", "tick", "shutdown"):
            if entry.get(key) is not None and not isinstance(entry.get(key), str):
                errors.append(f"entry.{key} must be a string or null")
    return errors


def write_manifest(path: Path, manifest: dict) -> None:
    errors = validate_manifest(manifest)
    if errors:
        raise ValueError("; ".join(errors))
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def read_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_leb_u32(data: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if pos >= len(data) or shift > 35:
            raise ValueError("invalid LEB128 u32")
        b = data[pos]
        pos += 1
        result |= (b & 0x7f) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7


def read_name(data: bytes, pos: int) -> tuple[str, int]:
    length, pos = read_leb_u32(data, pos)
    end = pos + length
    if end > len(data):
        raise ValueError("truncated WASM name")
    return data[pos:end].decode("utf-8", "replace"), end


def custom_sections(wasm: bytes, wanted: str | None = None) -> list[bytes]:
    if wasm[:4] != b"\x00asm":
        raise ValueError("not a WebAssembly binary")
    if len(wasm) < 8:
        raise ValueError("truncated WebAssembly header")
    pos = 8
    result = []
    while pos < len(wasm):
        section_id = wasm[pos]
        pos += 1
        size, pos = read_leb_u32(wasm, pos)
        end = pos + size
        if end > len(wasm):
            raise ValueError("truncated WebAssembly section")
        if section_id == 0:
            name, payload_pos = read_name(wasm, pos)
            if wanted is None or name == wanted:
                result.append(wasm[payload_pos:end])
        pos = end
    return result


def metadata(wasm: bytes) -> list[dict]:
    result = []
    for raw in custom_sections(wasm, META_SECTION):
        try:
            result.append(json.loads(raw.decode("utf-8")))
        except Exception as exc:
            result.append({"error": str(exc)})
    return result
