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


      log("=== C2 RUNTIME STATE ===");
      check("CRT started", e.x86_crt_get_started(), 1);
      check("CRT initial errno", e.x86_crt_get_errno(), 0);
      check("CRT initial last error", e.x86_crt_get_last_error(), 0);
      check("CRT initial exited", e.x86_crt_get_exited(), 0);
      check("CRT initial exit code", e.x86_crt_get_exit_code(), 0);
      check("CRT set errno", e.x86_crt_set_errno(-7), -7);
      check("CRT get errno", e.x86_crt_get_errno(), -7);
      check("CRT set last error", e.x86_crt_set_last_error(0xc2), 0xc2);
      check("CRT get last error", e.x86_crt_get_last_error(), 0xc2);
      check("CRT startup reset", e.x86_crt_startup(), 1);
      check("CRT errno reset", e.x86_crt_get_errno(), 0);
      check("CRT last error reset", e.x86_crt_get_last_error(), 0);

      let c2Callback = 0;
      const view = getView();
      for (let p = 0x00401000; p + 8 < 0x00402000; p++) {
        if (view[p] !== 0xb8) continue;
        const target = (view[p + 1] | (view[p + 2] << 8) | (view[p + 3] << 16) | (view[p + 4] << 24)) >>> 0;
        if (target >= 0x00401000 && target + 8 < view.length &&
            view[target] === 0x55 && view[target + 1] === 0x89 && view[target + 2] === 0xe5 &&
            view[target + 3] === 0x8b && view[target + 4] === 0x45 && view[target + 5] === 0x08 &&
            view[target + 6] === 0xc9 && view[target + 7] === 0xc3) {
          c2Callback = target;
          break;
        }
      }
      check("C2 callback fixture found", c2Callback !== 0, true);
      check("C2 direct callback", e.x86_crt_invoke_callback(c2Callback), 0xc2c0ffee | 0);
      check("C2 atexit register A", e.x86_crt_atexit(c2Callback), 1);
      check("C2 atexit register B", e.x86_crt_atexit(c2Callback), 1);
      check("C2 atexit count", e.x86_crt_get_atexit_count(), 2);
      check("C2 atexit callback 0", e.x86_crt_get_atexit_callback(0), c2Callback);
      check("C2 atexit callback 1", e.x86_crt_get_atexit_callback(1), c2Callback);
      check("C2 exit callbacks", e.x86_crt_exit(7), 2);
      check("C2 atexit drained", e.x86_crt_get_atexit_count(), 0);
      check("C2 last callback result", e.x86_crt_get_last_atexit_result(), 0xc2c0ffee | 0);
      check("C2 exited", e.x86_crt_get_exited(), 1);
      check("C2 exit code", e.x86_crt_get_exit_code(), 7);
      check("C2 atexit after exit rejected", e.x86_crt_atexit(c2Callback), 0);
      check("C2 errno after rejected atexit", e.x86_crt_get_errno(), 22);

      log("=== C3 GAME VIRTUAL FILESYSTEM ===");
      const fsPath = e.x86_crt_malloc(0x100);
      const fsData = e.x86_crt_malloc(0x40);
      const fsRead = e.x86_crt_malloc(0x40);
      const fsWritten = e.x86_crt_malloc(0x40);
      getView().set(new TextEncoder().encode("data\\textures\\hero.bin\0"), fsPath);
      getView().set(new Uint8Array([72,69,76,76,79,0]), fsData);
      check("C3 mount resource", e.x86_fs_mount_file(fsPath, fsData, 5), 1);
      check("C3 normalized exists", e.x86_fs_exists(fsPath), 1);
      const fsReadHandle = e.x86_fs_open(fsPath, 1, 0);
      check("C3 open read", fsReadHandle >= 0x1000, true);
      check("C3 file size", e.x86_fs_size(fsReadHandle), 5);
      check("C3 read bytes", e.x86_fs_read(fsReadHandle, fsRead, 5), 5);
      check("C3 read content", getView()[fsRead] === 72 && getView()[fsRead + 4] === 79, true);
      check("C3 seek start", e.x86_fs_seek(fsReadHandle, 0, 0), 0);
      check("C3 seek end", e.x86_fs_seek(fsReadHandle, -1, 2), 4);
      check("C3 close read", e.x86_fs_close(fsReadHandle), 1);

      getView().set(new TextEncoder().encode("saves\\score.dat\0"), fsPath);
      getView().set(new Uint8Array([1,2,3,4]), fsWritten);
      const fsWriteHandle = e.x86_fs_open(fsPath, 2, 4 | 8);
      check("C3 create write", fsWriteHandle >= 0x1000, true);
      check("C3 write bytes", e.x86_fs_write(fsWriteHandle, fsWritten, 4), 4);
      check("C3 write size", e.x86_fs_size(fsWriteHandle), 4);
      check("C3 close write", e.x86_fs_close(fsWriteHandle), 1);

      getView().set(new TextEncoder().encode("saves/./score.dat\0"), fsPath);
      const fsAppendHandle = e.x86_fs_open(fsPath, 1, 0);
      check("C3 normalized reopen", fsAppendHandle >= 0x1000, true);
      check("C3 reopened byte", e.x86_fs_read(fsAppendHandle, fsRead, 4), 4);
      check("C3 persisted byte", getView()[fsRead + 3], 4);
      check("C3 close reopen", e.x86_fs_close(fsAppendHandle), 1);

      getView().set(new TextEncoder().encode("../escape.bin\0"), fsPath);
      check("C3 path escape rejected", e.x86_fs_open(fsPath, 1 | 2, 4), 0);
      check("C3 path error", e.x86_fs_get_last_error(), 3);

      log("=== C4 VIRTUAL REGISTRY ===");
      const regPath = e.x86_crt_malloc(0x100);
      const regPath2 = e.x86_crt_malloc(0x100);
      const regName = e.x86_crt_malloc(0x100);
      const regData = e.x86_crt_malloc(0x100);
      const regOut = e.x86_crt_malloc(0x20);
      const regType = e.x86_crt_malloc(0x20);
      const regSize = e.x86_crt_malloc(0x20);
      const regBinary = e.x86_crt_malloc(0x100);
      const HKCU = 0x80000001;
      getView().set(new TextEncoder().encode("Software\\MyGame\\Settings\\Display\0"), regPath);
      check("C4 create key", e.x86_reg_create_key(HKCU, regPath, regOut), 0);
      const c4Key = new DataView(getView().buffer).getUint32(regOut, true);
      check("C4 key handle", c4Key >= 0x2000, true);
      check("C4 key exists", e.x86_reg_key_exists(HKCU, regPath), 1);
      getView().set(new TextEncoder().encode("Software/MyGame/Settings/./Display\0"), regPath2);
      check("C4 normalized key lookup", e.x86_reg_key_exists(HKCU, regPath2), 1);
      getView().set(new TextEncoder().encode("InstallPath\0"), regName);
      getView().set(new TextEncoder().encode("C:\\Games\\MyGame\0"), regData);
      check("C4 set REG_SZ", e.x86_reg_set_value(c4Key, regName, 1, regData, 16), 0);
      getView().fill(0, regType, regType + 4);
      new DataView(getView().buffer).setUint32(regSize, 0x100, true);
      check("C4 query REG_SZ", e.x86_reg_query_value(c4Key, regName, regType, regData, regSize), 0);
      check("C4 REG_SZ type", new DataView(getView().buffer).getUint32(regType, true), 1);
      check("C4 REG_SZ size", new DataView(getView().buffer).getUint32(regSize, true), 16);
      check("C4 REG_SZ content", new TextDecoder().decode(getView().slice(regData, regData + 16)) === "C:\\Games\\MyGame\0", true);

      const dwordView = new DataView(getView().buffer);
      dwordView.setUint32(regData, 1, true);
      getView().set(new TextEncoder().encode("Fullscreen\0"), regName);
      check("C4 set REG_DWORD", e.x86_reg_set_value(c4Key, regName, 4, regData, 4), 0);
      dwordView.setUint32(regSize, 4, true);
      check("C4 query REG_DWORD", e.x86_reg_query_value(c4Key, regName, regType, regData, regSize), 0);
      check("C4 REG_DWORD value", dwordView.getUint32(regData, true), 1);

      getView().set(new Uint8Array([1,2,3,4,5,6,7,8]), regBinary);
      getView().set(new TextEncoder().encode("Settings\0"), regName);
      check("C4 set REG_BINARY", e.x86_reg_set_value(c4Key, regName, 3, regBinary, 8), 0);
      dwordView.setUint32(regSize, 8, true);
      getView().fill(0, regData, regData + 8);
      check("C4 query REG_BINARY", e.x86_reg_query_value(c4Key, regName, regType, regData, regSize), 0);
      check("C4 REG_BINARY content", getView().slice(regData, regData + 8).every((v, i) => v === i + 1), true);
      check("C4 value exists", e.x86_reg_value_exists(c4Key, regName), 1);
      getView().set(new TextEncoder().encode("Missing\0"), regName);
      check("C4 missing value rejected", e.x86_reg_query_value(c4Key, regName, regType, regData, regSize), 2);
      check("C4 missing value error", e.x86_reg_get_last_error(), 2);
      getView().set(new TextEncoder().encode("Settings\0"), regName);
      check("C4 delete value", e.x86_reg_delete_value(c4Key, regName), 0);
      check("C4 value no longer exists", e.x86_reg_value_exists(c4Key, regName), 0);
      check("C4 close key", e.x86_reg_close_key(c4Key), 0);
      check("C4 invalid key rejected", e.x86_reg_close_key(0xdead), 6);
      check("C4 invalid key error", e.x86_reg_get_last_error(), 6);

      check("C4 free path", e.x86_crt_free(regPath), 1);
      check("C4 free path2", e.x86_crt_free(regPath2), 1);
      check("C4 free name", e.x86_crt_free(regName), 1);
      check("C4 free data", e.x86_crt_free(regData), 1);
      check("C4 free out", e.x86_crt_free(regOut), 1);
      check("C4 free type", e.x86_crt_free(regType), 1);
      check("C4 free size", e.x86_crt_free(regSize), 1);
      check("C4 free binary", e.x86_crt_free(regBinary), 1);

      check("C3 free path", e.x86_crt_free(fsPath), 1);
      check("C3 free data", e.x86_crt_free(fsData), 1);
      check("C3 free read buffer", e.x86_crt_free(fsRead), 1);
      check("C3 free write buffer", e.x86_crt_free(fsWritten), 1);

      const stress = [];
      for (let i = 0; i < 40; i++) {
        const p = e.x86_virtual_alloc(0x1000);
        if (!p) throw new Error("[FAIL] stress allocation " + i);
        stress.push(p);
      }
      check("region table after stress", e.x86_get_memory_region_count(), initialRegions + 4 + stress.length);
      for (const p of stress) check("stress region valid", e.x86_mem_validate(p, 0x1000, 3), 1);
      for (const p of stress) check("free stress region", e.x86_virtual_free(p), 1);

      check("regions after stress frees", e.x86_get_memory_region_count(), initialRegions + 4);
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

