# x86-to-wasm-packager

This repository contains a proof-of-concept packaging system for taking a 32-bit x86 Windows executable and wrapping it in a browser-loadable bundle. It is designed to support a browser-based boot shell and a custom JavaScript/WASM execution pipeline.

## Goals

- Accept a PE32 executable (`.exe`)
- Validate that it is x86 32-bit
- Extract metadata and section information
- Produce a package layout that can be booted via HTML + JavaScript
- Give a clear path toward a WASM-backed or original emulation environment

## Supported input

- Windows 32-bit PE files (x86 / `IMAGE_FILE_MACHINE_I386`)

## Output format

The generated bundle contains:

- `manifest.json` — metadata describing the executable and package
- `payload.bin` — a copy of the original executable
- `index.html` — a boot shell to load the package in a browser
- `loader.js` — JavaScript bootloader that loads the package and surfaces payload metadata

## Requirements

- Python 3.9+
- Modern browser with fetch support

## Usage

```bash
python3 tool/packager.py /path/to/your_app.exe --output dist/your_app
```

Then serve the output directory:

```bash
cd dist/your_app
python3 -m http.server 8000
```

Open:

```text
http://localhost:8000/index.html
```

## Generated package example

```json
{
  "bundle_version": "1.0",
  "name": "your_app",
  "architecture": "x86",
  "machine": "i386",
  "entry_point": "0x401000",
  "file_size": 123456,
  "sections": [
    {"name": ".text", "virtual_address": 4096, "size": 4096},
    {"name": ".data", "virtual_address": 8192, "size": 2048}
  ],
  "payload": "payload.bin",
  "loader": "loader.js"
}
```

## Implementation notes

This repository is intentionally modular:

- The Python tool performs validation and packaging
- The JS layer is where a browser or WASM runtime can attach execution logic
- The boot shell is a generic container that makes the bundle look like a self-contained app shell

## Important limitation

This is not a complete universal emulator. It packages and prepares a PE32 for browser booting. Real execution depends on an emulator or WASM runtime that understands the x86 instruction set and the app's OS/system expectations.

## Next steps

- Add WASM bridge support
- Add support for 16-bit DOS payloads
- Add a custom emulator stub for instruction execution
- Add custom packaging for a dedicated HTML shell environment

