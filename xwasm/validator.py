from __future__ import annotations

import json
from pathlib import Path

from .format import custom_sections, metadata, validate_manifest
from .container import KIND_XAPI, KIND_XPL, KIND_XWASM, unpack_bytes
from .xapi import validate_manifest as validate_xapi_manifest


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
        payload_format = manifest.get("payload_format")
        if isinstance(payload_name, str) and payload_name:
            try:
                payload_path = _safe_package_path(root, payload_name, "payload")
                if not payload_path.is_file():
                    errors.append(f"missing payload: {payload_name!r}")
                else:
                    data = payload_path.read_bytes()
                    if payload_format == "XPL" or data.startswith(b"XWSC01"):
                        try:
                            _, data = unpack_bytes(data, expected_kind=KIND_XPL)
                        except ValueError as exc:
                            errors.append(f"invalid XPL payload: {exc}")
                            data = b""
                    if data:
                        if data[:2] != b"MZ":
                            errors.append("x86 payload does not have an MZ/PE header")
                        elif len(data) < 0x40:
                            errors.append("x86 payload is too small to be a PE file")
                        else:
                            pe = int.from_bytes(data[0x3C:0x40], "little")
                            if pe + 24 > len(data) or data[pe:pe + 4] != b"PE\0\0":
                                errors.append("x86 payload does not contain a valid PE header")
                            elif int.from_bytes(data[pe + 4:pe + 6], "little") != 0x014C:
                                errors.append("x86 payload is not i386 PE32")
                            elif int.from_bytes(data[pe + 24:pe + 26], "little") != 0x010B:
                                errors.append("x86 payload is not PE32 (optional-header magic 0x010B)")
            except ValueError as exc:
                errors.append(str(exc))

        runtime_name = manifest.get("runtime")
        if runtime_name:
            try:
                runtime_path = _safe_package_path(root, runtime_name, "runtime")
                if not runtime_path.is_file():
                    errors.append(f"missing runtime: {runtime_name!r}")
                else:
                    data = runtime_path.read_bytes()
                    if data.startswith(b"XWSC01"):
                        try:
                            _, wasm = unpack_bytes(data, expected_kind=KIND_XWASM)
                        except ValueError as exc:
                            errors.append(f"invalid XWASM runtime container: {exc}")
                            wasm = b""
                        if wasm and not wasm.startswith(b"\x00asm"):
                            errors.append("unpacked XWASM runtime does not have a WebAssembly binary header")
                    elif data.startswith(b"\x00asm"):
                        warnings.append("x86 package uses legacy raw runtime.wasm; prefer runtime.xwasm")
                    else:
                        errors.append("x86 runtime is neither an XWASM container nor a WebAssembly binary")
            except ValueError as exc:
                errors.append(str(exc))
        else:
            warnings.append("x86 package has no runtime; it requires an external/host-supplied x86 runtime")

        xapi_pool_name=manifest.get("xapi_pool")
        if xapi_pool_name:
            # The package-local pool is the only authoritative runtime XAPI
            # artifact. Source/plain .xapi files must not be loaded as a second
            # registry input by browser shells.
            pool_resolved=(root / xapi_pool_name).resolve()
            for stray in sorted(root.rglob("*.xapi")):
                if stray.resolve()!=pool_resolved:
                    warnings.append(f"stray XAPI artifact in package (not loaded): {stray.relative_to(root).as_posix()}")

            try:
                xapi_pool_path=_safe_package_path(root,xapi_pool_name,"xapi_pool")
                if not xapi_pool_path.is_file():
                    errors.append(f"missing xapi_pool: {xapi_pool_name!r}")
                else:
                    try:
                        _,xapi_raw=unpack_bytes(xapi_pool_path.read_bytes(),expected_kind=KIND_XAPI)
                        xapi_manifest=json.loads(xapi_raw.decode("utf-8-sig"))
                        errors.extend(f"xapi_pool: {e}" for e in validate_xapi_manifest(xapi_manifest))
                    except (ValueError,json.JSONDecodeError) as exc:
                        errors.append(f"invalid XAPI pool: {exc}")
            except ValueError as exc:
                errors.append(str(exc))
        else:
            warnings.append("x86 package has no package-local xapi_pool; runtime API registry must be supplied externally")

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

    # Static-recompilation packages contain translated WASM plus a
    # guest image/data blob. The source PE is build provenance only.
    if architecture == "x86-recompiled":
        module_name = manifest.get("module")
        image_name = manifest.get("image")
        for label, name in (("module", module_name), ("image", image_name)):
            if not isinstance(name, str) or not name:
                errors.append(f"{label} must be a non-empty string for x86-recompiled packages")
                continue
            try:
                path = _safe_package_path(root, name, label)
                if not path.is_file():
                    errors.append(f"missing {label}: {name!r}")
            except ValueError as exc:
                errors.append(str(exc))

        if isinstance(module_name, str) and module_name:
            try:
                module_path = _safe_package_path(root, module_name, "module")
                if module_path.is_file():
                    wasm = module_path.read_bytes()
                    if not wasm.startswith(b"\\x00asm"):
                        errors.append("recompiled module does not have a WebAssembly binary header")
                    else:
                        try:
                            metas = metadata(wasm)
                            if not metas:
                                warnings.append("recompiled module has no xwasm.meta custom section")
                        except ValueError as exc:
                            errors.append(f"invalid recompiled module metadata: {exc}")
            except ValueError as exc:
                errors.append(str(exc))

        resource_root = manifest.get("resource_root")
        if isinstance(resource_root, str):
            try:
                resource_path = _safe_package_path(root, resource_root, "resource_root")
                if not resource_path.is_dir():
                    errors.append(f"missing resource_root: {resource_root!r}")
            except ValueError as exc:
                errors.append(str(exc))
        else:
            errors.append("resource_root must be a string")

        return {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "manifest": manifest,
            "architecture": "x86-recompiled",
            "module_bytes": ((root / module_name).stat().st_size
                             if isinstance(module_name, str) and (root / module_name).is_file() else 0),
            "image_bytes": ((root / image_name).stat().st_size
                            if isinstance(image_name, str) and (root / image_name).is_file() else 0),
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
    if not wasm.startswith(b"\x00asm"):
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
