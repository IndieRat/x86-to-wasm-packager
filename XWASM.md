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
## Reference boot protocol

The reference runner follows this sequence:

1. Read `manifest.xwasm.json`.
2. Require `format = xwasm-package` and `format_version = 1`.
3. Require ABI `xwasm.host/1`.
4. Load the declared module as bytes.
5. Call `WebAssembly.validate()`.
6. Compile the module.
7. Inspect declared imports and exports.
8. Provide the `xwasm.host` import namespace.
9. Instantiate the module.
10. Resolve the manifest lifecycle exports.
11. Call init, one test tick, then shutdown.

Generate a dummy package:

    python3 tool/xwasm_reference_package.py --output ./dist/xwasm-reference.xwasm

Generate a standalone browser runner for that package:

    python3 tool/xwasm_reference_runner.py ./dist/xwasm-reference.xwasm --output ./dist/xwasm-reference.html

The runner is intentionally a reference shell rather than a game runtime. Its purpose is to establish observable boot behavior that OWB can reproduce later.

## X86 runtime v0.1 test pipeline

Build the runtime WebAssembly module:

    python3 tool/xwasm_build_x86_runtime.py --output ./dist/x86-runtime-v0.1/runtime.wasm

Build a deterministic XWASM x86 test package containing that runtime, a tiny synthetic PE32 payload, and a manifest:

    python3 tool/xwasm_build_x86_test.py --output ./dist/x86-runtime-test.xwasm

Inspect the package before using the browser runner:

    python3 tool/xwasm_inspect.py ./dist/x86-runtime-test.xwasm

The synthetic payload is only a loader/runtime fixture; it is not a Windows game. A real game is the next test stage and is exported with tool/xwasm_pack_x86.py.


## X86 runtime v0.4 import + memory foundation

The x86 compatibility runtime now has the first executable Win32 compatibility layer primitives:

- a guest heap arena at 0x00800000..0x01F00000, separate from the diagnostic/WASM allocator;
- exported x86_alloc(size) for guest-visible allocations;
- PE import-directory parsing that walks import descriptors and thunk tables;
- builtin DLL/function resolution for the initial compatibility seed: KERNEL32.dll!GetTickCount;
- IAT patching with runtime-owned API addresses;
- indirect CALL r/m32 (FF /2) support for resolved imports;
- a host-call bridge that can execute the builtin API without pretending the browser contains a native Windows DLL;
- import diagnostics for resolved/unresolved counts and the last resolved target.

The deterministic x86 test fixture now contains a real PE32 import directory and calls the resolved KERNEL32!GetTickCount entry through its IAT. The browser runner verifies both the import resolution and the guest allocator before executing the CPU/import test.

This is deliberately a seed compatibility layer rather than a complete Windows DLL implementation. Additional KERNEL32, CRT/C++ runtime, USER32, graphics, file, audio, and input APIs should be added from the target executable's actual import table as later milestones.


## X86 runtime v0.5 Win32 memory foundation

The x86 runtime now extends the v0.4 import/memory seed with a small virtual-memory compatibility layer:

- KERNEL32.dll!VirtualAlloc resolved through the builtin import table;
- KERNEL32.dll!VirtualFree resolved through the builtin import table;
- Win32-style stack arguments for these APIs (stdcall-shaped guest calls);
- page-aligned guest virtual-memory allocation from a dedicated arena at 0x02000000..0x06000000;
- deterministic allocation diagnostics including last allocation address/size and free-call count;
- a synthetic PE32 test that imports XWASMHOST!xwasm_log, KERNEL32!VirtualAlloc, KERNEL32!VirtualFree, and KERNEL32!GetTickCount;
- the browser runner verifies the allocation, release call, final GetTickCount result, and 23-instruction execution path.

This is intentionally a compatibility seed, not a complete Windows virtual-memory implementation. Real Windows VirtualAlloc/VirtualFree support includes page state, reservation/commit semantics, protection flags, and additional failure conditions; the runtime currently models the subset needed to establish the guest memory ABI and execution path. Microsoft documents VirtualAlloc as reserving/committing pages and VirtualFree as releasing or decommitting regions.


## X86 runtime v0.6 graphics foundation

The x86 runtime now has a first browser-backed Win32 graphics surface. This is intentionally a compatibility bridge, not a full USER32/GDI32 implementation.

The v0.6 seed resolves:

- USER32.dll!CreateWindowExA
- USER32.dll!ShowWindow
- USER32.dll!GetDC
- USER32.dll!ReleaseDC
- GDI32.dll!SetPixel
- GDI32.dll!Rectangle

The browser host exposes a Canvas 2D surface. CreateWindowExA creates the runtime's logical window surface, ShowWindow/GetDC provide compatible handles, and selected GDI calls are translated into Canvas drawing operations. The deterministic fixture draws a rectangle and a pixel through the x86 -> USER32/GDI32 -> browser path.

Microsoft documents CreateWindowEx/ShowWindow as the normal Win32 window creation/showing path and GDI Rectangle/SetPixel as drawing APIs. citeturn2search0turn2search2turn1search0turn0search0

This milestone deliberately does not claim complete Windows window management, message dispatch, painting, device contexts, brushes, pens, DirectX/OpenGL, or compositor behavior. Those will be added only as the target game's actual imports and runtime behavior require them.

The next graphics work should establish a persistent frame buffer/presentation path, basic window-message/input plumbing, and then the APIs needed by the real target executable.
