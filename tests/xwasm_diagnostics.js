function readSemantic(e, index) {
  const len = e.x86_get_trace_semantic_id_len(index);
  let s = "";
  for (let i = 0; i < len; i++) s += String.fromCharCode(e.x86_get_trace_semantic_id_char(index, i));
  return s || "<none>";
}

function printDiagnostics(e, label, options = {}) {
  const hex32 = n => (n >>> 0).toString(16).padStart(8, "0");
  const hex8 = n => (n & 255).toString(16).padStart(2, "0");
  const current = e.x86_get_eip() >>> 0;
  console.log(`=== ${label} CPU FAILURE DIAGNOSTICS ===`);
  console.log(`[FAULT] run result=${options.runResult ?? "<n/a>"} cpu_error=0x${hex32(e.x86_get_cpu_error())} halted=${e.x86_get_halted()}`);
  console.log(`[FAULT] current EIP=0x${hex32(current)} steps=${e.x86_get_steps()}`);
  console.log("[FAULT] next 32 bytes=" +
    Array.from({length: 32}, (_, i) => hex8(e.x86_get_current_byte(i))).join(" "));
  console.log("[FAULT] last opcode=0x" + hex8(e.x86_get_last_decoded_opcode()) +
    " map=0x" + hex32(e.x86_get_last_decoded_map()) +
    " length=" + e.x86_get_last_decoded_length() +
    " dispatch=" + e.x86_get_last_dispatch_id() +
    " dispatch_count=" + e.x86_get_last_dispatch_count());
  const slen = e.x86_get_last_semantic_id_len();
  let sid = "";
  for (let i = 0; i < slen; i++) sid += String.fromCharCode(e.x86_get_last_semantic_id_char(i));
  console.log("[FAULT] last semantic=" + (sid || "<none>"));
  console.log("[FAULT] current imm32=0x" + hex32(e.x86_get_current_imm32()));
  console.log("[FAULT] regs" +
    " EAX=0x" + hex32(e.x86_get_eax()) +
    " ECX=0x" + hex32(e.x86_get_ecx()) +
    " EDX=0x" + hex32(e.x86_get_edx()) +
    " EBX=0x" + hex32(e.x86_get_ebx()) +
    " ESP=0x" + hex32(e.x86_get_esp()) +
    " EBP=0x" + hex32(e.x86_get_ebp()) +
    " ESI=0x" + hex32(e.x86_get_esi()) +
    " EDI=0x" + hex32(e.x86_get_edi()));
  console.log("[FAULT] EFLAGS=0x" + hex32(e.x86_get_eflags()) +
    " x87_depth=" + e.x86_get_x87_count() +
    " memory_faults=" + e.x86_get_memory_faults() +
    " memory_regions=" + e.x86_get_memory_region_count());
  console.log("[FAULT] stack=" +
    Array.from({length: 16}, (_, i) => "0x" + hex32(e.x86_get_stack_dword(i))).join(" "));
  const tc = e.x86_get_trace_count();
  const failure = e.x86_get_trace_failure_index();
  console.log("[FAULT] trace_count=" + tc + " trace_failure_index=" + failure);
  const start = options.fullTrace ? 0 : Math.max(0, tc - 64);
  for (let j = start; j < tc; j++) {
    const i = e.x86_get_trace_index(j);
    console.log("[FAULT TRACE " + String(j).padStart(3, "0") + "] EIP=0x" +
      hex32(e.x86_get_trace_eip(i)) + " -> 0x" + hex32(e.x86_get_trace_next_eip(i)) +
      " OP=0x" + hex8(e.x86_get_trace_opcode(i)) +
      " SEM=" + readSemantic(e, i) +
      " DISPATCH=" + e.x86_get_trace_dispatch(i) +
      " EAX=0x" + hex32(e.x86_get_trace_eax(i)) +
      " FLAGS=0x" + hex32(e.x86_get_trace_flags(i)));
  }
  console.log("=== END " + label + " CPU FAILURE DIAGNOSTICS ===");
}

function diagnosticCheck(e, name, actual, expected, options = {}) {
  if ((actual >>> 0) !== (expected >>> 0)) {
    printDiagnostics(e, options.label || "XWASM", options);
    throw new Error(`[FAIL] ${name}: got ${actual >>> 0}, expected ${expected >>> 0}`);
  }
  console.log(`[PASS] ${name}: ${actual >>> 0}`);
}

module.exports = { printDiagnostics, diagnosticCheck };
