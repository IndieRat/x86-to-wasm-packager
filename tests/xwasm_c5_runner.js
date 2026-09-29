(() => {
  const $ = id => document.getElementById(id);
  const log = s => {
    const p = document.createElement("div");
    p.textContent = s;
    $("log").appendChild(p);
  };
  const check = (name, actual, expected) => {
    if (actual !== expected) throw new Error("[FAIL] " + name + ": got " + actual + ", expected " + expected);
    log("[PASS] " + name + ": " + actual);
  };
  const hex = n => "0x" + (n >>> 0).toString(16).padStart(8, "0");

  async function run() {
    $("log").textContent = "";
    const runtimeFile = $("runtime").files[0];
    const payloadFile = $("payload").files[0];
    if (!runtimeFile || !payloadFile) {
      log("Select runtime.wasm and the compiled C5 PE32 fixture first.");
      return;
    }

    try {
      const runtimeBytes = await runtimeFile.arrayBuffer();
      const payload = new Uint8Array(await payloadFile.arrayBuffer());
      const module = await WebAssembly.compile(runtimeBytes);
      const env = {};
      let memory = null;
      for (const imp of WebAssembly.Module.imports(module)) {
        if (imp.module !== "env") continue;
        if (imp.kind === "memory") {
          memory = new WebAssembly.Memory({initial: 1024, maximum: 4096});
          env[imp.name] = memory;
        } else if (imp.kind === "function") {
          env[imp.name] = () => 0;
        }
      }
      const instance = await WebAssembly.instantiate(module, {env});
      const e = instance.exports;
      if (!memory) throw new Error("runtime did not import memory");
      const view = () => new Uint8Array(memory.buffer);
      const payloadAddress = 0x00100000;
      view().set(payload, payloadAddress);

      log("=== C5 COMPILED C INTEGRATION ===");
      check("runtime version", e.x86_get_runtime_version(), 0x00090000);
      check("init", e.xwasm_init(), 0);
      check("PE load", e.x86_load_pe(payloadAddress, payload.length), 0);
      check("loaded", e.x86_get_loaded(), 1);
      check("load error", e.x86_get_load_error(), 0);

      const result = e.x86_run(10000);
      log("[INFO] CPU run=" + result + " steps=" + e.x86_get_steps() +
          " EIP=" + hex(e.x86_get_eip()) + " EAX=" + hex(e.x86_get_eax()) +
          " ESP=" + hex(e.x86_get_esp()));
      check("CPU halted", e.x86_get_halted(), 1);
      check("CPU error", e.x86_get_cpu_error(), 0);
      check("compiled C return value", e.x86_get_eax(), 3);

      const path = e.x86_crt_malloc(0x40);
      const keyPath = e.x86_crt_malloc(0x80);
      const valueName = e.x86_crt_malloc(0x40);
      const queryData = e.x86_crt_malloc(0x20);
      const queryType = e.x86_crt_malloc(0x20);
      const querySize = e.x86_crt_malloc(0x20);
      view().set(new TextEncoder().encode("saves/c5.dat\0"), path);
      check("C5 filesystem state", e.x86_fs_exists(path), 1);

      view().set(new TextEncoder().encode("Software/C5/Runtime\0"), keyPath);
      const HKCU = 0x80000001;
      check("C5 registry key state", e.x86_reg_key_exists(HKCU, keyPath), 1);
      view().set(new TextEncoder().encode("Milestone\0"), valueName);
      check("C5 registry value state", e.x86_reg_value_exists(e.x86_reg_open_key(HKCU, keyPath, queryData) === 0
        ? new DataView(view().buffer).getUint32(queryData, true) : 0, valueName), 1);

      const key = new DataView(view().buffer).getUint32(queryData, true);
      new DataView(view().buffer).setUint32(querySize, 4, true);
      check("C5 registry query", e.x86_reg_query_value(key, valueName, queryType, queryData, querySize), 0);
      check("C5 registry type", new DataView(view().buffer).getUint32(queryType, true), 4);
      check("C5 registry value", new DataView(view().buffer).getUint32(queryData, true), 0xC5);

      check("C5 close registry key", e.x86_reg_close_key(key), 0);
      e.x86_crt_free(path); e.x86_crt_free(keyPath); e.x86_crt_free(valueName);
      e.x86_crt_free(queryData); e.x86_crt_free(queryType); e.x86_crt_free(querySize);

      log("=== RESULT ===");
      log("[PASS] XWASM C5 compiled-C integration milestone complete");
    } catch (err) {
      log(String(err));
    }
  }

  $("run").addEventListener("click", run);
})();
