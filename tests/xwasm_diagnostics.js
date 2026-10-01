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
  const err = e.x86_get_cpu_error() >>> 0;
  const opcode = e.x86_get_last_decoded_opcode() >>> 0;
  const stage = (err & 0xFF00) === 0xD000 ? "decode" : (err ? "execute" : "none");
  console.log(`[FAULT] run result=${options.runResult ?? "<n/a>"} cpu_error=0x${hex32(err)} stage=${stage} halted=${e.x86_get_halted()}`);
  console.log(`[FAULT] fault EIP=0x${hex32(current)} opcode=0x${hex8(opcode)} bytes_consumed=${e.x86_get_last_decoded_length()}`);
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
  if (e.x86_get_last_decoded_length() > 0) {
    console.log("[FAULT] decoded semantic=" + (sid || "<none>") + " next_eip=0x" + hex32((current + e.x86_get_last_decoded_length()) >>> 0));
  }
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
    const post = typeof e.x86_get_trace_post_eax === "function";
    const postText = post
      ? " POST[EAX=0x" + hex32(e.x86_get_trace_post_eax(i)) +
        " ECX=0x" + hex32(e.x86_get_trace_post_ecx(i)) +
        " EDX=0x" + hex32(e.x86_get_trace_post_edx(i)) +
        " EBX=0x" + hex32(e.x86_get_trace_post_ebx(i)) +
        " FLAGS=0x" + hex32(e.x86_get_trace_post_flags(i)) + "]"
      : "";
    console.log("[FAULT TRACE " + String(j).padStart(3, "0") + "] EIP=0x" +
      hex32(e.x86_get_trace_eip(i)) + " -> 0x" + hex32(e.x86_get_trace_next_eip(i)) +
      " OP=0x" + hex8(e.x86_get_trace_opcode(i)) +
      " SEM=" + readSemantic(e, i) +
      " DISPATCH=" + e.x86_get_trace_dispatch(i) +
      " PRE[EAX=0x" + hex32(e.x86_get_trace_eax(i)) +
      " ECX=0x" + hex32(e.x86_get_trace_ecx(i)) +
      " EDX=0x" + hex32(e.x86_get_trace_edx(i)) +
      " EBX=0x" + hex32(e.x86_get_trace_ebx(i)) +
      " FLAGS=0x" + hex32(e.x86_get_trace_flags(i)) + "]" + postText);
  }
  console.log("=== END " + label + " CPU FAILURE DIAGNOSTICS ===");
}

function diagnosticCheck(e, name, actual, expected, options = {}) {
  if (actual !== expected) {
    printDiagnostics(e, options.label || "XWASM", options);
    throw new Error(`[FAIL] ${name}: got ${actual}, expected ${expected}`);
  }
  console.log(`[PASS] ${name}: ${actual}`);
}

module.exports = { printDiagnostics, diagnosticCheck };
