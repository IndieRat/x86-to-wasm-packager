const fs = require("fs");

const wasmPath = process.argv[2];
if (!wasmPath) throw new Error("usage: node xwasm_cpu_memory_stress.js runtime.wasm");

const bytes = fs.readFileSync(wasmPath);
const module = new WebAssembly.Module(bytes);
const imports = WebAssembly.Module.imports(module);
const env = {};
let importedMemory = null;

for (const imp of imports) {
  if (imp.module !== "env") continue;
  if (imp.kind === "memory") {
    importedMemory = new WebAssembly.Memory({initial: 1024, maximum: 4096});
    env[imp.name] = importedMemory;
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
  if (actual !== expected) {
    throw new Error(`[FAIL] ${name}: got ${actual}, expected ${expected}`);
  }
  console.log(`[PASS] ${name}: ${actual}`);
};
const hex = n => `0x${n.toString(16).padStart(8, "0")}`;

check("runtime version", e.x86_get_runtime_version(), 0x00090000);
check("init", e.xwasm_init(), 0);
check("initial region count", e.x86_get_memory_region_count(), 0);
check("initial faults", e.x86_get_memory_faults(), 0);

if (!importedMemory) throw new Error("[FAIL] runtime did not import a memory");
const view = new Uint8Array(importedMemory.buffer);

// Basic region contract.
const a = e.x86_virtual_alloc(0x1000);
check("allocation A nonzero", a !== 0, true);
check("A writable", e.x86_mem_validate(a, 0x1000, 2), 1);
check("A readable", e.x86_mem_validate(a, 0x1000, 1), 1);
check("A executable rejected", e.x86_mem_validate(a, 0x1000, 4), 0);
check("fault count after execute rejection", e.x86_get_memory_faults(), 1);

// Boundary checks: the byte immediately before the end is valid;
// the first byte after the region is not.
check("A last byte readable", e.x86_mem_validate(a + 0xfff, 1, 1), 1);
check("A end rejected", e.x86_mem_validate(a + 0x1000, 1, 1), 0);
check("fault count after boundary rejection", e.x86_get_memory_faults(), 2);

// Exercise the actual backing WASM memory through the runtime helpers.
check("memset A", e.x86_mem_set(a, 0x5a, 0x1000), 1);
check("A byte 0", view[a], 0x5a);
check("A byte end", view[a + 0xfff], 0x5a);

// Force the allocator toward the stack boundary. The current runtime has
// a stack region at 0x03E00000..0x03EFFFFF. A 28 MiB allocation ends at
// 0x03C00000, so the following 4 MiB allocation would overlap the stack
// unless the allocator skips the occupied region.
const nearStack = e.x86_virtual_alloc(0x01c00000);
check("near-stack allocation", nearStack, 0x02001000);
const afterStack = e.x86_virtual_alloc(0x00400000);
if (!afterStack) throw new Error("[FAIL] post-stack allocation returned zero");

const stackBase = 0x03e00000;
const stackEnd = 0x03f00000;
const afterStackEnd = afterStack + 0x00400000;
const overlapsStack = afterStack < stackEnd && afterStackEnd > stackBase;
check("allocator avoids stack overlap", overlapsStack, false);
check("post-stack allocation writable", e.x86_mem_validate(afterStack, 0x00400000, 2), 1);
check("stack remains readable/writable", e.x86_mem_validate(stackBase, 0x1000, 3), 1);

// Copy across a large allocation and verify bytes at both ends.
check("memset near-stack region", e.x86_mem_set(nearStack, 0xa5, 0x01c00000), 1);
check("copy near-stack -> A", e.x86_mem_copy(a, nearStack, 0x1000), 1);
check("copied first byte", view[a], 0xa5);
check("copied last byte", view[a + 0xfff], 0xa5);

// Freeing must remove the region from validation.
check("free A", e.x86_virtual_free(a), 1);
check("freed A rejected", e.x86_mem_validate(a, 1, 1), 0);
check("fault count after freed access", e.x86_get_memory_faults(), 3);
check("free count", e.x86_get_virtual_free_count(), 1);

// Invalid bulk operations must be rejected and accounted as faults.
check("invalid copy rejected", e.x86_mem_copy(a, nearStack, 1), 0);
check("fault count after invalid copy", e.x86_get_memory_faults(), 4);
check("invalid memset rejected", e.x86_mem_set(a, 0, 1), 0);
check("fault count after invalid memset", e.x86_get_memory_faults(), 5);

// Stress the region table without consuming meaningful guest address space.
const stress = [];
for (let i = 0; i < 60; i++) {
  const p = e.x86_virtual_alloc(0x1000);
  if (!p) throw new Error(`[FAIL] stress allocation ${i} returned zero`);
  stress.push(p);
}
check("region count after stress allocations", e.x86_get_memory_region_count(), 62);

// Every live allocation should remain readable/writable.
for (let i = 0; i < stress.length; i++) {
  if (e.x86_mem_validate(stress[i], 0x1000, 3) !== 1) {
    throw new Error(`[FAIL] stress region ${i} invalid at ${hex(stress[i])}`);
  }
}
console.log("[PASS] all stress allocations remain valid");

// Free the stress set and verify the region table drains without corrupting
// the two large live regions.
for (const p of stress) {
  check(`free stress ${hex(p)}`, e.x86_virtual_free(p), 1);
}
check("region count after stress frees", e.x86_get_memory_region_count(), 2);
check("near-stack region survives stress", e.x86_mem_validate(nearStack, 0x1000, 3), 1);
check("post-stack region survives stress", e.x86_mem_validate(afterStack, 0x1000, 3), 1);

console.log("[PASS] XWASM v0.9 CPU + guest-memory stress test complete");
