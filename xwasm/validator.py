from __future__ import annotations

import json
from pathlib import Path

from .format import custom_sections, metadata, validate_manifest


def validate_package(root: Path) -> dict:
    root = root.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    manifest_path = root / "manifest.xwasm.json"
    if not manifest_path.is_file():
        errors.append("missing manifest.xwasm.json")
        return {"valid": False, "errors": errors, "warnings": warnings}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"valid": False, "errors": [f"invalid manifest JSON: {exc}"], "warnings": warnings}
    errors.extend(validate_manifest(manifest))
    module_path = root / manifest.get("module", "")
    if not module_path.is_file():
        errors.append(f"missing module: {manifest.get('module')!r}")
        return {"valid": False, "errors": errors, "warnings": warnings}
    wasm = module_path.read_bytes()
    if not wasm.startswith(b"\\x00asm"):
        errors.append("module does not have a WebAssembly binary header")
    else:
        try:
            metas = metadata(wasm)
            if not metas:
                warnings.append("module has no xwasm.meta custom section")
            for meta in metas:
                if meta.get("format") != "xwasm-meta" or meta.get("version") != 1:
                    warnings.append("module contains an unrecognized xwasm.meta version")
                elif meta.get("abi") != manifest.get("abi"):
                    errors.append("xwasm.meta ABI does not match manifest ABI")
        except ValueError as exc:
            errors.append(str(exc))
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "manifest": manifest,
        "module_bytes": len(wasm),
    }
