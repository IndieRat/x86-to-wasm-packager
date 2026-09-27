# XWASM Package Format

XWASM is this repository's package/host convention built on top of standard WebAssembly. It does not replace or fork WebAssembly.

## Design goals
- Keep standard .wasm modules valid standard WebAssembly.
- Make the HTML shell independent of a particular emulator/runtime.
- Define one predictable package signature and ABI.
- Support offline loading without requiring URL fetches for package contents.
- Treat resources as a virtual package filesystem.
- Allow different runtimes to implement the same host contract.
- Keep x86 execution as a runtime capability, not a property magically provided by a PE file.

## Package signature
A directory package is identified by `manifest.xwasm.json` with `format = "xwasm-package"` and a semantic `format_version`.

A future single-file container may use the ASCII magic `XWASM\\0` followed by a versioned container header. The directory format is the first implementation target.

```text
MyGame.xwasm/
├── manifest.xwasm.json
├── game.wasm
├── bridge.js
└── resources/
    └── ...
```

## WebAssembly side
The game/runtime remains ordinary WebAssembly. XWASM does not add new opcodes.

The module may expose the conventional lifecycle exports `xwasm_init()`, `xwasm_tick(delta_ms)`, and `xwasm_shutdown()`. These are conventions, not new WebAssembly instructions.

The module may import host functions under `xwasm.host`. Initial ABI names are `log`, `resource_size`, `resource_read`, `time_ms`, and `exit`. Exact signatures are versioned by the ABI and described in the manifest.

## Custom metadata section
A WASM module may contain a custom section named `xwasm.meta`. Custom sections are standard WebAssembly section type 0 and are ignored by WebAssembly execution semantics, allowing metadata without changing the executable instruction set.

The initial payload is UTF-8 JSON:

```json
{
  "format": "xwasm-meta",
  "version": 1,
  "abi": "xwasm.host/1"
}
```

## Package manifest
Reference:

```json
{
  "format": "xwasm-package",
  "format_version": 1,
  "name": "Example",
  "architecture": "wasm32",
  "module": "game.wasm",
  "bridge": null,
  "resource_root": "resources/",
  "abi": "xwasm.host/1",
  "entry": {
    "init": "xwasm_init",
    "tick": "xwasm_tick",
    "shutdown": "xwasm_shutdown"
  }
}
```

For an x86 compatibility runtime, the manifest can additionally identify `runtime/runtime.wasm` and `payload.bin`. The payload is not itself WASM; the runtime must actually execute or translate it.

## Host responsibilities
1. Recognize the manifest signature.
2. Validate manifest version and ABI.
3. Load the declared WASM module as bytes.
4. Inspect imports/exports.
5. Construct the XWASM host import object.
6. Instantiate the module.
7. Resolve lifecycle exports.
8. Provide virtual resource access.
9. Report errors without silently falling back to unrelated loaders.

## Resource model
Resources are package data, not necessarily browser URLs. A runtime requests a normalized path such as `textures/player.png`; the host resolves it under `resources/`.

This permits imported File objects, ArrayBuffers, IndexedDB-backed data, or HTTP resources without changing the game/runtime ABI.

## Runtime model
```text
package format
     ↓
host ABI
     ↓
runtime
     ↓
execution engine
```

An x86 runtime may contain an x86 interpreter, translator, or emulator compiled to WebAssembly. The package itself does not claim that a PE executable has been converted into WASM.

## Versioning
- `format_version` versions package structure.
- `abi` versions host imports and resource semantics.
- Runtime-specific versions belong in runtime metadata.
- Unknown future fields should be ignored where safe.
- A major ABI mismatch must fail clearly instead of guessing.

## Reference implementation
- `xwasm/format.py` — manifest/signature helpers.
- `xwasm/validator.py` — package and WASM validation.
- `tool/xwasm_inspect.py` — command-line inspection.
- `tool/xwasm_pack.py` — package an existing WASM module and resources.
- `runtime/reference/host.js` — minimal browser host ABI reference.

The first milestone is intentionally a native WASM package. Once that works, an x86 compatibility runtime can implement the same contract.

## What XWASM is not
XWASM is not a new WebAssembly instruction set, browser standard, CPU architecture, or universal EXE converter.

It is a project-specific packaging and host ABI convention that uses standard WebAssembly facilities.