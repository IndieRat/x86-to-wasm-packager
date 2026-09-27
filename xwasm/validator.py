from __future__ import annotations

import json
from pathlib import Path

from .format import custom_sections, metadata, validate_manifest


def _safe_package_path(root: Path, relative: str, label: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError(f"{label} points outside the XWASM package: {relative!r}")
    return path


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
    architecture = manifest.get("architecture")

    # X86 packages intentionally do not contain a native game.wasm module.
    if architecture == "x86":
        payload_name = manifest.get("payload")
        if isinstance(payload_name, str) and payload_name:
            try:
                payload_path = _safe_package_path(root, payload_name, "payload")
                if not payload_path.is_file():
                    errors.append(f"missing payload: {payload_name!r}")
                else:
                    data = payload_path.read_bytes()
                    if data[:2] != b"MZ":
                        errors.append("x86 payload does not have an MZ/PE header")
                    elif len(data) < 0x40:
                        errors.append("x86 payload is too small to be a PE file")
            except ValueError as exc:
                errors.append(str(exc))

        runtime_name = manifest.get("runtime")
        if runtime_name:
            try:
                runtime_path = _safe_package_path(root, runtime_name, "runtime")
                if not runtime_path.is_file():
                    errors.append(f"missing runtime: {runtime_name!r}")
                elif not runtime_path.read_bytes().startswith(b"\x00asm"):
                    errors.append("x86 runtime does not have a WebAssembly binary header")
            except ValueError as exc:
                errors.append(str(exc))
        else:
            warnings.append("x86 package has no runtime.wasm; it requires an external/host-supplied x86 runtime")

        resource_root = manifest.get("resource_root")
        if isinstance(resource_root, str):
            try:
                resource_path = _safe_package_path(root, resource_root, "resource_root")
                if not resource_path.is_dir():
                    errors.append(f"missing resource_root: {resource_root!r}")
            except ValueError as exc:
                errors.append(str(exc))

        return {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "manifest": manifest,
            "architecture": "x86",
            "payload_bytes": (
                (root / payload_name).stat().st_size
                if isinstance(payload_name, str)
                and payload_name
                and (root / payload_name).is_file()
                else 0
            ),
        }

    # Native WASM package validation.
    module_name = manifest.get("module")
    if not isinstance(module_name, str) or not module_name:
        errors.append("module must be a non-empty string for wasm32 packages")
        return {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "manifest": manifest,
            "architecture": architecture,
        }

    try:
        module_path = _safe_package_path(root, module_name, "module")
    except ValueError as exc:
        errors.append(str(exc))
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "manifest": manifest,
            "architecture": "wasm32",
        }

    if not module_path.is_file():
        errors.append(f"missing module: {module_name!r}")
        return {"valid": False, "errors": errors, "warnings": warnings, "manifest": manifest, "architecture": "wasm32"}

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
        "architecture": "wasm32",
        "module_bytes": len(wasm),
    }
