const fs = require("fs");

const runtimePath = process.argv[2];
const payloadPath = process.argv[3];

if (!runtimePath || !payloadPath) {
  throw new Error("usage: node xwasm_cpu_stress.js runtime.wasm payload.exe");
}

const runtimeBytes = fs.readFileSync(runtimePath);
const payload = fs.readFileSync(payloadPath);

const module = new WebAssembly.Module(runtimeBytes);
const imports = WebAssembly.Module.imports(module);
const env = {};
let importedMemory = null;

for (const imp of imports) {
  if (imp.module !== "env") continue;
  if (imp.kind === "memory") {
    importedMemory = new WebAssembly.Memory({initial: 1024, maximum: 4096});
    env[imp.name] = importedMemory;
  } else if (imp.kind === "function") {
    env[imp.name] = (...args) => imp.name === "xwasm_input_poll" ? 0 : 0;
  }
}

const instance = new WebAssembly.Instance(module, {env});
const e = instance.exports;
const check = (name, actual, expected) => {
  if (actual !== expected) throw new Error(`[FAIL] ${name}: got ${actual}, expected ${expected}`);
  console.log(`[PASS] ${name}: ${actual}`);
};
const hex = n => `0x${(n >>> 0).toString(16).padStart(8, "0")}`;

check("runtime version", e.x86_get_runtime_version(), 0x00090000);
check("init", e.xwasm_init(), 0);
if (!importedMemory) throw new Error("[FAIL] runtime did not import memory");

const getView = () => new Uint8Array(importedMemory.buffer);
const payloadAddress = 0x00100000;
if (payloadAddress + payload.length > getView().length) {
  throw new Error("[FAIL] payload does not fit in imported memory");
}
getView().set(payload, payloadAddress);

check("PE load", e.x86_load_pe(payloadAddress, payload.length), 0);
check("loaded", e.x86_get_loaded(), 1);
check("load error", e.x86_get_load_error(), 0);
check("image base", e.x86_get_image_base(), 0x00400000);
check("entry nonzero", e.x86_get_eip() !== 0, true);

const runResult = e.x86_run(2000);
console.log(`[INFO] CPU run result=${runResult} steps=${e.x86_get_steps()} EIP=${hex(e.x86_get_eip())} EAX=${hex(e.x86_get_eax())} EFLAGS=${hex(e.x86_get_eflags())}`);
check("CPU halted", e.x86_get_halted(), 1);
check("C0 callback return preserved", e.x86_get_esi(), 0x2a);
check("CPU error", e.x86_get_cpu_error(), 0);
check("CPU executed instructions", e.x86_get_steps() > 0, true);
check("RCR architectural self-test", e.x86_rcr32_self_test(), 0);

const traceCount = e.x86_get_trace_count();
check("trace populated", traceCount > 0, true);
console.log(`[PASS] CPU trace entries: ${traceCount}`);
console.log(`[INFO] legacy executions=${e.x86_get_legacy_execution_count()} refined dispatches=${e.x86_get_last_dispatch_count()}`);

const report = [];
for (let i = 0; i < 16; i++) report.push(e.x86_get_stress_report_word(i) >>> 0);
console.log("[INFO] stress report:", report.map(hex).join(" "));

// Guest-memory phase runs after PE load so the runtime has image, heap, and
// stack regions registered. This directly exercises the v0.9 VM allocator.
check("initial post-PE faults", e.x86_get_memory_faults(), 0);
const initialRegions = e.x86_get_memory_region_count();
console.log(`[INFO] PE memory regions=${initialRegions}`);

const a = e.x86_virtual_alloc(0x1000);
check("allocation A nonzero", a !== 0, true);
check("A writable", e.x86_mem_validate(a, 0x1000, 2), 1);
check("A readable", e.x86_mem_validate(a, 0x1000, 1), 1);
check("A executable rejected", e.x86_mem_validate(a, 0x1000, 4), 0);
check("fault count after execute rejection", e.x86_get_memory_faults(), 1);
check("A last byte readable", e.x86_mem_validate(a + 0xfff, 1, 1), 1);
check("A end rejected", e.x86_mem_validate(a + 0x1000, 1, 1), 0);
check("fault count after boundary rejection", e.x86_get_memory_faults(), 2);

check("memset A", e.x86_mem_set(a, 0x5a, 0x1000), 1);
check("A byte 0", getView()[a], 0x5a);
check("A byte end", getView()[a + 0xfff], 0x5a);

const stackBase = 0x03e00000;
const stackEnd = 0x03f00000;
const nearStack = e.x86_virtual_alloc(0x01c00000);
if (!nearStack) throw new Error("[FAIL] near-stack allocation returned zero");
console.log(`[PASS] near-stack allocation: ${hex(nearStack)}`);

const afterStack = e.x86_virtual_alloc(0x00400000);
if (!afterStack) throw new Error("[FAIL] post-stack allocation returned zero");
const afterStackEnd = afterStack + 0x00400000;
const overlapsStack = afterStack < stackEnd && afterStackEnd > stackBase;
check("allocator avoids stack overlap", overlapsStack, false);
check("post-stack allocation writable", e.x86_mem_validate(afterStack, 0x00400000, 2), 1);
check("stack remains readable/writable", e.x86_mem_validate(stackBase, 0x1000, 3), 1);

check("memset near-stack region", e.x86_mem_set(nearStack, 0xa5, 0x01c00000), 1);
check("copy near-stack -> A", e.x86_mem_copy(a, nearStack, 0x1000), 1);
check("copied first byte", getView()[a], 0xa5);
check("copied last byte", getView()[a + 0xfff], 0xa5);

check("free A", e.x86_virtual_free(a), 1);
check("freed A rejected", e.x86_mem_validate(a, 1, 1), 0);
check("fault count after freed access", e.x86_get_memory_faults(), 3);
check("free count", e.x86_get_virtual_free_count(), 1);

check("invalid copy rejected", e.x86_mem_copy(a, nearStack, 1), 0);
check("fault count after invalid copy", e.x86_get_memory_faults(), 4);
check("invalid memset rejected", e.x86_mem_set(a, 0, 1), 0);
check("fault count after invalid memset", e.x86_get_memory_faults(), 5);

console.log("=== C1 MEMORY / CRT ===");
const c1a = e.x86_crt_malloc(0x40);
const c1b = e.x86_crt_malloc(0x40);
check("CRT malloc A", c1a !== 0, true);
check("CRT malloc B", c1b !== 0, true);
check("CRT A writable", e.x86_mem_validate(c1a, 0x40, 2), 1);
check("CRT A readable", e.x86_mem_validate(c1a, 0x40, 1), 1);
check("CRT invalid pointer rejected", e.x86_mem_validate(c1a + 0x40, 1, 1), 0);
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

const stress = [];
for (let i = 0; i < 40; i++) {
  const p = e.x86_virtual_alloc(0x1000);
  if (!p) throw new Error(`[FAIL] stress allocation ${i} returned zero`);
  stress.push(p);
}
check("region count after 40 stress allocations", e.x86_get_memory_region_count(), initialRegions + 2 + stress.length);

for (let i = 0; i < stress.length; i++) {
  if (e.x86_mem_validate(stress[i], 0x1000, 3) !== 1) {
    throw new Error(`[FAIL] stress region ${i} invalid at ${hex(stress[i])}`);
  }
}
console.log("[PASS] all stress allocations remain readable/writable");

for (const p of stress) check(`free stress ${hex(p)}`, e.x86_virtual_free(p), 1);
check("region count after stress frees", e.x86_get_memory_region_count(), initialRegions + 2);
check("near-stack region survives", e.x86_mem_validate(nearStack, 0x1000, 3), 1);
check("post-stack region survives", e.x86_mem_validate(afterStack, 0x1000, 3), 1);

console.log("[PASS] XWASM v0.9 CPU + guest-memory stress test complete");

