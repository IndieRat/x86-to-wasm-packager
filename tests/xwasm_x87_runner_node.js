const fs = require("fs");

function fail(message) {
  console.error("[FAIL] " + message);
  process.exit(1);
}

function check(name, actual, expected) {
  if (actual !== expected) {
    fail(name + ": got " + actual + ", expected " + expected);
  }
  console.log("[PASS] " + name + ": " + actual);
}

function hex(n) {
  return "0x" + (n >>> 0).toString(16).padStart(8, "0");
}

async function main() {
  const runtimePath = process.argv[2];
  const payloadPath = process.argv[3];
  if (!runtimePath || !payloadPath) {
    fail("usage: node tests/xwasm_x87_runner_node.js runtime.wasm x87-fixture.exe");
  }

  const runtime = fs.readFileSync(runtimePath);
  const payload = fs.readFileSync(payloadPath);
  const module = await WebAssembly.compile(runtime);

  const env = {};
  let memory = null;
  for (const imp of WebAssembly.Module.imports(module)) {
    if (imp.module !== "env") continue;
    if (imp.kind === "memory") {
      memory = new WebAssembly.Memory({ initial: 1024, maximum: 4096 });
      env[imp.name] = memory;
    } else if (imp.kind === "function") {
      env[imp.name] = () => 0;
    }
  }

  const instance = await WebAssembly.instantiate(module, { env });
  const e = instance.exports;
  if (!memory) fail("runtime did not import memory");

  const view = new Uint8Array(memory.buffer);
  const addr = 0x00100000;
  view.set(payload, addr);

  console.log("=== X87 COMPILED C INTEGRATION ===");
  check("runtime version", e.x86_get_runtime_version(), 0x00090000);
  check("init", e.xwasm_init(), 0);
  check("PE load", e.x86_load_pe(addr, payload.length), 0);
  check("loaded", e.x86_get_loaded(), 1);
  check("load error", e.x86_get_load_error(), 0);

  const result = e.x86_run(10000);
  const eip = e.x86_get_eip() >>> 0;
  console.log("[INFO] CPU run=" + result +
              " steps=" + e.x86_get_steps() +
              " EIP=" + hex(eip) +
              " EAX=" + hex(e.x86_get_eax()));

  let semantic = "";
  for (let i = 0; i < e.x86_get_last_semantic_id_len(); i++) {
    semantic += String.fromCharCode(e.x86_get_last_semantic_id_char(i));
  }
  console.log("[DEBUG] semantic ID: " + (semantic || "<none>"));

  check("CPU halted", e.x86_get_halted(), 1);
  check("CPU error", e.x86_get_cpu_error(), 0);
  check("x87 compiled C result", e.x86_get_eax(), 1);
  console.log("=== RESULT ===");
  console.log("[PASS] XWASM x87 compiled-C milestone complete");
}

main().catch(err => fail(err && err.stack ? err.stack : String(err)));
