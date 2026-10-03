# x86-to-wasm-packager

Packages a 32-bit x86 Windows game folder into a browser-ready x86/WASM package.

## Folder -> package

Given:

```text
MyGame/
├── Game.exe
├── data/
├── textures/
├── sounds/
└── config/
```

Run:

```bash
python3 tool/packager.py ./MyGame --output ./dist/MyGame
```

The tool validates the selected PE32 executable, copies it to `payload.bin`, and copies the rest of the game folder under `resources/`.

If you have a real x86 execution/translation runtime:

```bash
python3 tool/packager.py ./MyGame \
  --output ./dist/MyGame \
  --runtime-wasm ./runtime.wasm \
  --bridge ./bridge.js
```

The output is:

```text
dist/MyGame/
├── index.html
├── loader.js
├── manifest.json
├── payload.bin
├── runtime.wasm
├── bridge.js
└── resources/
    ├── data/
    ├── textures/
    ├── sounds/
    └── config/
```

## Multiple executables

Use `--exe` when the folder contains several executables:

```bash
python3 tool/packager.py ./MyGame \
  --exe bin/GameLauncher.exe \
  --output ./dist/MyGame
```

## Test

The generated shell uses `fetch()`, so serve the output:

```bash
cd dist/MyGame
python3 -m http.server 8000
```

Then open `http://localhost:8000/index.html`.

## Important limitation

This repository is a **packaging layer**, not a universal Windows emulator. A random Windows EXE is not converted into WebAssembly by this Python script.

For actual execution, `runtime.wasm` must contain the x86 execution/translation layer and support the Windows APIs, filesystem, graphics, audio, input, and other facilities required by the game. The generated `loader.js` exposes the package data so that a compatible runtime or bridge can consume it.

The package format is intentionally simple so the browser side can be matched to the actual runtime ABI.

## Runtime bundle and existing-port updates

The packager does not generate an x86 CPU emulator/translator. `runtime.wasm` is an actual execution/translation engine supplied separately. A compatible `bridge.js` connects that runtime to the package.

Put a compatible pair in one directory:

```text
runtime/
├── runtime.wasm
└── bridge.js
```

Build a package with that pair:

```bash
python3 tool/packager.py ./MyGame --output ./dist/MyGame --runtime-dir ./runtime
```

Or supply the files individually with `--runtime-wasm` and `--bridge`.

### Update an existing port

You can add the runtime later without rebuilding the game files:

```bash
python3 tool/packager.py --update-port ./dist/MyGame --runtime-dir ./runtime
```

This preserves `payload.bin` and `resources/`, copies/replaces `runtime.wasm` and `bridge.js`, updates `manifest.json`, and refreshes `loader.js`.

The generated bridge expects the real runtime to expose:

```js
window.X86Runtime.start({ payload, manifest, readResource })
```

If a runtime uses another ABI, provide its matching bridge with `--bridge`.

Important: a package containing a PE32 executable is not itself a browser-native WASM executable. The runtime must actually implement x86 execution/translation and the compatibility facilities required by the target game.

## Built-in guest disk builder

The packager can now create a raw `guest.hda` without requiring QEMU to be installed:

```bash
python3 tool/packager.py ./MyGame \
  --output ./dist/MyGame \
  --runtime-dir ./runtime \
  --guest-auto \
  --guest-size 2G
```

This creates a real raw `guest.hda` alongside the package files.

`guest.hda` is initially **blank**. The builder intentionally does not bundle or install an operating system. A guest OS must be installed before v86 can boot it. v86 supports hard-disk images directly, including images supplied as buffers.

You can also use the standalone builder:

```bash
python3 tool/guest_builder.py --output ./guest.hda --size 2G
```

Or copy an existing raw guest image:

```bash
python3 tool/guest_builder.py \
  --output ./guest.hda \
  --from-image ./existing.img
```

This removes the need to use `qemu-img` merely to create an empty disk. It does not turn a blank disk into a Windows installation, and it does not automatically install a game into the guest OS.

## XWASM format and host ABI

The repository now defines XWASM, a project-specific package and host convention built on standard WebAssembly. It does not modify the WebAssembly instruction set.

See `XWASM.md` for the format and ABI specification.

A first native-WASM package can be created with:

    python3 tool/xwasm_pack.py ./game.wasm --output ./dist/game.xwasm --resources ./resources

Inspect it with:

    python3 tool/xwasm_inspect.py ./dist/game.xwasm

The reference browser host lives at `runtime/reference/host.js`.

The migration plan is:

    XWASM package
        ↓
    XWASM host ABI
        ↓
    native WASM runtime
        OR
    x86 compatibility runtime compiled to WASM
        ↓
    HTML shell

The existing x86/v86 package tools remain available during this migration. They are not treated as the XWASM ABI itself.

## XWASM x86 runtime v0.1

The repository includes the first x86 compatibility-runtime foundation:

- runtime/x86/runtime.c — PE32 loader, import/DLL inventory, and tiny x86 instruction-stepper foundation.
- tool/xwasm_build_x86_runtime.py — builds the runtime as standard WebAssembly and permits unresolved host imports.
- tool/xwasm_build_x86_test.py — creates a deterministic runtime test package with a synthetic PE32 payload and manifest.
- tool/xwasm_pack_x86.py — exports a real 32-bit Windows game folder, records bundled DLLs, and can bundle an externally built runtime.wasm.
- tool/xwasm_x86_runner.py — browser runner for the current x86 loader milestone.

Recommended order:

1. Build and inspect the deterministic x86 runtime test package.
2. Run its generated XWASM browser runner and verify PE staging/loading.
3. Export a real 32-bit game with tool/xwasm_pack_x86.py and the same runtime.wasm.
4. Only then continue expanding CPU instructions, DLL/API resolution, memory mapping, graphics, audio, input, and filesystem support.

The v0.1 runtime is a bring-up foundation, not yet a complete Windows compatibility layer.

## XWASM C5 compiled-C integration fixture

C5 moves the milestone suite from isolated runtime-export tests to a real compiler-generated 32-bit C program.

Build the fixture with LLVM/Clang and lld-link:

    python3 tool/xwasm_build_c5_fixture.py --output ./dist/c5-fixture.exe

The fixture is freestanding C and does not depend on a Windows CRT. It uses cdecl calls into the XWASM game-runtime ABI for:

- checked CRT allocation and string handling
- virtual game filesystem mount/open/read/close
- virtual registry key/value creation and storage

The C5 browser runner is tests/xwasm_c5_runner.html. It expects the rebuilt runtime.wasm and the compiled C5 PE32 fixture.

C5 intentionally uses direct cdecl XWASM compatibility addresses (the 0x70010000 range) rather than pretending these are normal Windows DLL exports. This keeps the fixture focused on the CPU/ABI/runtime integration boundary; real MSVCRT/ADVAPI32 import compatibility remains a later expansion.


## XWASM x86 build fixture series

The `tool/xwasm_build_*` scripts are the executable compatibility-fixture series. They are deterministic PE32 guests used to validate the runtime and browser bridges incrementally before running real games.

Current progression includes:

- `tool/xwasm_build_x86_runtime.py` — builds the XWASM x86 runtime container.
- `tool/xwasm_build_x86_graphics_test.py` — Win32/GDI graphics surface bring-up.
- `tool/xwasm_build_x86_window_input_audio_test.py` — USER32 message/input, window, GDI, and KERNEL32 audio bridge coverage.
- `tool/xwasm_build_x86_opengl_pong_test.py` — OpenGL-style window/input/audio Pong seed using `OPENGL32.dll`, `GDI32.dll`, `USER32.dll`, and `KERNEL32.dll` compatibility imports.
- `tests/xwasm_opengl_pong/index.html` — browser shell that supplies the graphics, window/input, and Web Audio host bridges required by the Pong fixture.

Build the OpenGL Pong seed after building the v0.9 runtime:

    python3 tool/xwasm_build_x86_runtime.py --clang /path/to/clang.exe
    python3 tool/xwasm_build_x86_opengl_pong_test.py --output ./dist/xwasm-opengl-pong

The Pong fixture is intentionally a **bring-up seed**, not the final gameplay stress test. Its initial milestone is successful PE loading, Win32 window/DC setup, pixel-format/WGL setup, OpenGL draw calls, buffer presentation, audio, and one input-bridge poll. Once that milestone is green, the next test replaces the deterministic completion path with a persistent Pong loop so CPU branches, CALL/RET, stack discipline, message polling, input state, repeated OpenGL rendering, collision/update logic, and frame-to-frame host synchronization can be stress-tested under real gameplay.
