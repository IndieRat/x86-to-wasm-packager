(() => {
  const $ = id => document.getElementById(id);
  const log = (s, cls = "") => {
    const p = document.createElement("div");
    p.className = cls;
    p.textContent = s;
    $("log").appendChild(p);
    $("log").scrollTop = $("log").scrollHeight;
  };
  const hex = n => "0x" + (n >>> 0).toString(16).padStart(8, "0");

  async function run() {
    $("log").textContent = "";
    const runtimeFile = $("runtime").files[0];
    const payloadFile = $("payload").files[0];
    if (!runtimeFile || !payloadFile) {
      log("Select runtime.wasm and payload.exe first.", "fail");
      return;
    }

    try {
      log("Loading runtime.wasm...");
      const runtimeBytes = await runtimeFile.arrayBuffer();
      const payload = new Uint8Array(await payloadFile.arrayBuffer());
      const module = await WebAssembly.compile(runtimeBytes);
      const env = {};
      let importedMemory = null;

      for (const imp of WebAssembly.Module.imports(module)) {
        if (imp.module !== "env") continue;
        if (imp.kind === "memory") {
          importedMemory = new WebAssembly.Memory({initial: 1024, maximum: 4096});
          env[imp.name] = importedMemory;
        } else if (imp.kind === "function") {
          env[imp.name] = () => 0;
        }
      }

      const instance = await WebAssembly.instantiate(module, {env});
      const e = instance.exports;
      if (!importedMemory) throw new Error("runtime did not import memory");
      const getView = () => new Uint8Array(importedMemory.buffer);

      const check = (name, actual, expected) => {
        if (actual !== expected) throw new Error("[FAIL] " + name + ": got " + actual + ", expected " + expected);
        log("[PASS] " + name + ": " + actual, "pass");
      };

      check("runtime version", e.x86_get_runtime_version(), 0x00090000);
      check("init", e.xwasm_init(), 0);

      const payloadAddress = 0x00100000;
      if (payloadAddress + payload.length > getView().length) throw new Error("payload does not fit in WASM memory");
      getView().set(payload, payloadAddress);

      log("=== CPU / PE32 ===");
      check("PE load", e.x86_load_pe(payloadAddress, payload.length), 0);
      check("loaded", e.x86_get_loaded(), 1);
      check("load error", e.x86_get_load_error(), 0);

      const result = e.x86_run(2000);
      log("[INFO] CPU run=" + result + " steps=" + e.x86_get_steps() +
          " EIP=" + hex(e.x86_get_eip()) + " EAX=" + hex(e.x86_get_eax()) +
          " EFLAGS=" + hex(e.x86_get_eflags()));
      check("CPU halted", e.x86_get_halted(), 1);
      check("C0 callback return preserved", e.x86_get_esi(), 0x2a);
      check("CPU error", e.x86_get_cpu_error(), 0);
      check("RCR architectural self-test", e.x86_rcr32_self_test(), 0);
      if (e.x86_get_trace_count() === 0) throw new Error("[FAIL] CPU trace is empty");
      log("[PASS] CPU trace entries: " + e.x86_get_trace_count(), "pass");
      log("[INFO] legacy executions=" + e.x86_get_legacy_execution_count() +
          " refined dispatches=" + e.x86_get_last_dispatch_count());

      log("=== GUEST MEMORY ===");
      const initialRegions = e.x86_get_memory_region_count();
      check("initial memory faults", e.x86_get_memory_faults(), 0);

      const a = e.x86_virtual_alloc(0x1000);
      check("allocation A", a !== 0, true);
      check("A readable", e.x86_mem_validate(a, 0x1000, 1), 1);
      check("A writable", e.x86_mem_validate(a, 0x1000, 2), 1);
      check("A executable rejected", e.x86_mem_validate(a, 0x1000, 4), 0);
      check("fault count", e.x86_get_memory_faults(), 1);

      check("A last byte", e.x86_mem_validate(a + 0xfff, 1, 1), 1);
      check("A end rejected", e.x86_mem_validate(a + 0x1000, 1, 1), 0);
      check("boundary fault count", e.x86_get_memory_faults(), 2);

      check("memset A", e.x86_mem_set(a, 0x5a, 0x1000), 1);
      check("A byte 0", getView()[a], 0x5a);
      check("A byte end", getView()[a + 0xfff], 0x5a);

      const stackBase = 0x03e00000, stackEnd = 0x03f00000;
      const nearStack = e.x86_virtual_alloc(0x01c00000);
      if (!nearStack) throw new Error("[FAIL] near-stack allocation");
      log("[PASS] near-stack allocation: " + hex(nearStack), "pass");

      const afterStack = e.x86_virtual_alloc(0x00400000);
      if (!afterStack) throw new Error("[FAIL] post-stack allocation");
      const overlap = afterStack < stackEnd && afterStack + 0x00400000 > stackBase;
      check("allocator avoids stack overlap", overlap, false);
      check("post-stack writable", e.x86_mem_validate(afterStack, 0x00400000, 2), 1);
      check("stack remains valid", e.x86_mem_validate(stackBase, 0x1000, 3), 1);

      check("large memset", e.x86_mem_set(nearStack, 0xa5, 0x01c00000), 1);
      check("large copy", e.x86_mem_copy(a, nearStack, 0x1000), 1);
      check("copied byte", getView()[a], 0xa5);

      check("free A", e.x86_virtual_free(a), 1);
      check("freed A rejected", e.x86_mem_validate(a, 1, 1), 0);
      check("fault count after free", e.x86_get_memory_faults(), 3);

      check("invalid copy rejected", e.x86_mem_copy(a, nearStack, 1), 0);
      check("fault count", e.x86_get_memory_faults(), 4);
      check("invalid memset rejected", e.x86_mem_set(a, 0, 1), 0);
      check("fault count", e.x86_get_memory_faults(), 5);

      log("=== C1 MEMORY / CRT ===");
      const c1a = e.x86_crt_malloc(0x40);
      const c1b = e.x86_crt_malloc(0x40);
      check("CRT malloc A", c1a !== 0, true);
      check("CRT malloc B", c1b !== 0, true);
      check("CRT A writable", e.x86_mem_validate(c1a, 0x40, 2), 1);
      check("CRT A readable", e.x86_mem_validate(c1a, 0x40, 1), 1);
      check("CRT cross-allocation pointer rejected", e.x86_mem_validate(c1a + 0x3f, 2, 1), 0);
      const c1Before = e.x86_get_memory_faults();
      getView().set(new Uint8Array([1,2,3,4,5,6,7,8]), c1a);
      check("CRT memcpy", e.x86_crt_memcpy(c1b, c1a, 8), c1b);
      check("CRT memcpy byte", getView()[c1b + 7], 8);
      check("CRT memset", e.x86_crt_memset(c1b + 8, 0xaa, 8), c1b + 8);
      check("CRT memset byte", getView()[c1b + 15], 0xaa);
      check("CRT memcmp equal", e.x86_crt_memcmp(c1a, c1a, 8), 0);
      getView()[c1b + 7] = 9;
      check("CRT memcmp ordering", e.x86_crt_memcmp(c1a, c1b, 8), -1);
      getView().set(new Uint8Array([1,2,3,4,5,6,7,8]), c1a);
      check("CRT memmove overlap", e.x86_crt_memmove(c1a + 2, c1a, 6), c1a + 2);
      check("CRT memmove overlap byte", getView()[c1a + 7], 6);
      const str = e.x86_crt_malloc(0x40);
      const str2 = e.x86_crt_malloc(0x40);
      getView().set(new TextEncoder().encode("hello C1\0"), str);
      check("CRT strlen", e.x86_crt_strlen(str), 8);
      check("CRT strcpy", e.x86_crt_strcpy(str2, str), str2);
      check("CRT strcmp equal", e.x86_crt_strcmp(str, str2), 0);
      getView()[str2 + 7] = 0x7a;
      check("CRT strcmp ordering", e.x86_crt_strcmp(str, str2), -1);
      const zeroed = e.x86_crt_calloc(8, 4);
      check("CRT calloc", zeroed !== 0, true);
      check("CRT calloc zero", getView()[zeroed + 31], 0);
      const resized = e.x86_crt_realloc(c1a, 0x80);
      check("CRT realloc", resized !== 0, true);
      check("CRT realloc preserves data", getView()[resized + 7], 6);
      check("CRT free A", e.x86_crt_free(resized), 1);
      check("CRT free B", e.x86_crt_free(c1b), 1);
      check("CRT free string", e.x86_crt_free(str), 1);
      check("CRT free string2", e.x86_crt_free(str2), 1);
      check("CRT free calloc", e.x86_crt_free(zeroed), 1);
      check("CRT freed pointer rejected", e.x86_mem_validate(resized, 1, 1), 0);
      check("CRT invalid operation faulted", e.x86_get_memory_faults(), c1Before + 1);

      const stress = [];
      for (let i = 0; i < 40; i++) {
        const p = e.x86_virtual_alloc(0x1000);
        if (!p) throw new Error("[FAIL] stress allocation " + i);
        stress.push(p);
      }
      check("region table after stress", e.x86_get_memory_region_count(), initialRegions + 2 + stress.length);
      for (const p of stress) check("stress region valid", e.x86_mem_validate(p, 0x1000, 3), 1);
      for (const p of stress) check("free stress region", e.x86_virtual_free(p), 1);

      check("regions after stress frees", e.x86_get_memory_region_count(), initialRegions + 2);
      check("near-stack survives", e.x86_mem_validate(nearStack, 0x1000, 3), 1);
      check("post-stack survives", e.x86_mem_validate(afterStack, 0x1000, 3), 1);

      log("=== RESULT ===");
      log("[PASS] XWASM v0.9 CPU + guest-memory stress test complete", "pass");
    } catch (err) {
      log(String(err && err.stack ? err.stack : err), "fail");
    }
  }

  $("run").addEventListener("click", run);
})();