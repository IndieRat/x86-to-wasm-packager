# x86-to-wasm-packager

A packaging tool and browser bootloader for 32-bit x86 Windows applications. The project packages a PE32 executable into a browser-friendly bundle and exposes a lightweight HTML/JavaScript host that can load the packaged payload and display boot metadata.

This is intentionally designed as a packaging and bridge layer rather than a universal x86 emulator. The project gives you a reproducible layout for turning a legacy x86 binary into a browser-hosted bundle, with a JS bootloader and metadata manifest so a custom emulator or WASM runtime can consume the payload.

## What this project does

- Validates a Windows 32-bit PE executable (`MZ` + `PE` format)
- Extracts metadata such as entry point, section table, binary size, and architecture
- Writes a package bundle that contains:
  - the original binary payload
  - a metadata manifest
  - a browser loader HTML page
  - a JS bootloader
- Produces a layout that can be served locally or remotely for a browser-based shell

## Repository layout

- `tool/packager.py` — CLI tool that packages a PE32 app into a browser bundle
- `web/index.html` — sample HTML shell for loading a packaged app
- `web/loader.js` — JavaScript bootloader that fetches a manifest and binary payload
- `docs/usage.md` — detailed usage and deployment notes
- `README.md` — project overview and quick start

## Quick start

1. Clone or update the repo.
2. Run the package tool against a 32-bit PE executable:

```bash
python3 tool/packager.py /path/to/app.exe --output dist/app
```

3. Serve the generated output directory:

```bash
cd dist/app
python3 -m http.server 8000
```

4. Open the browser shell:

```text
http://localhost:8000/index.html
```

## Example workflow

```bash
python3 tool/packager.py ./samples/legacy_app.exe --output ./dist/legacy-app
cd ./dist/legacy-app
python3 -m http.server 8000
```

Then point the browser at the generated index page and the bootloader will load the packaged payload.

## Notes

- This project does not claim to execute arbitrary 32-bit x86 Windows programs in pure JavaScript without a compatible emulator or WASM runtime.
- The generated package is best used as an integration layer that feeds a browser-side emulator, a WASM execution bridge, or a custom original boot environment.
- This is the packaging layer and bootstrapping format you asked for, designed around HTML + JS hosting.

## Future directions

- Add a WASM bridge that receives the packaged PE binary and exposes execution APIs
- Add a custom x86 decode layer or interpreter for selected instruction subsets
- Add support for a minimal VM object model for DOS-like or legacy app shells
- Add packaging for additional formats (ELF, COM, or custom system images)

## License

MIT
