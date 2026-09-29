const fs = require("fs");

const wasmPath = process.argv[2];
if (!wasmPath) throw new Error("usage: node xwasm_memory_selftest.js runtime.wasm");

const bytes = fs.readFileSync(wasmPath);
const module = new WebAssembly.Module(bytes);
const imports = WebAssembly.Module.imports(module);
const env = {};

for (const imp of imports) {
  if (imp.module !== "env") continue;
  if (imp.kind === "memory") {
    env[imp.name] = new WebAssembly.Memory({initial: 1024, maximum: 4096});
  } else if (imp.kind === "function") {
    env[imp.name] = (...args) => {
      if (imp.name === "xwasm_input_poll") return 0;
      return 0;
    };
  }
}

const instance = new WebAssembly.Instance(module, {env});
const e = instance.exports;
const check = (name, actual, expected) => {
  if (actual !== expected) throw new Error(`[FAIL] ${name}: got ${actual}, expected ${expected}`);
  console.log(`[PASS] ${name}: ${actual}`);
};

check("runtime version", e.x86_get_runtime_version(), 0x00090000);
check("init", e.xwasm_init(), 0);
check("initial region count", e.x86_get_memory_region_count(), 0);
check("initial faults", e.x86_get_memory_faults(), 0);

const a = e.x86_virtual_alloc(0x1000);
const b = e.x86_virtual_alloc(0x2000);
if (!a || !b || a === b) throw new Error(`[FAIL] allocations: a=0x${a.toString(16)} b=0x${b.toString(16)}`);
console.log(`[PASS] allocations: a=0x${a.toString(16)} b=0x${b.toString(16)}`);

check("region count after allocations", e.x86_get_memory_region_count(), 2);
check("a writable", e.x86_mem_validate(a, 0x1000, 2), 1);
check("a readable", e.x86_mem_validate(a, 0x1000, 1), 1);
check("a executable rejected", e.x86_mem_validate(a, 0x1000, 4), 0);
check("fault count after rejected exec", e.x86_get_memory_faults(), 1);

check("memset a", e.x86_mem_set(a, 0x5a, 0x1000), 1);
check("copy a -> b", e.x86_mem_copy(b, a, 0x1000), 1);

const mem = e.memory;
const view = new Uint8Array(mem.buffer);
check("copied byte 0", view[b], 0x5a);
check("copied byte 0x3ff", view[b + 0x3ff], 0x5a);

check("free a", e.x86_virtual_free(a), 1);
check("region count after free", e.x86_get_memory_region_count(), 1);
check("freed a rejected", e.x86_mem_validate(a, 1, 1), 0);
check("fault count after freed access", e.x86_get_memory_faults(), 2);
check("free count", e.x86_get_virtual_free_count(), 1);
check("b remains valid", e.x86_mem_validate(b, 0x2000, 3), 1);

console.log("[PASS] XWASM v0.9 memory self-test complete");
