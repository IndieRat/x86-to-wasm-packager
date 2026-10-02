(() => {
const $=id=>document.getElementById(id), log=(s,cls="")=>{const d=document.createElement("div");d.className=cls;d.textContent=s;$("log").appendChild(d)}, hex=n=>"0x"+(n>>>0).toString(16).padStart(8,"0");
const td=new TextDecoder();
function u64(v,o){const n=v.getBigUint64(o,true);if(n>BigInt(Number.MAX_SAFE_INTEGER))throw Error("container too large");return Number(n)}
async function unpack(buf,kind,name){
 const b=new Uint8Array(buf),v=new DataView(buf);if(b.length<62||td.decode(b.slice(0,6))!=="XWSC01")throw Error(name+" is not XWSC01");
 if(v.getUint16(6,true)!==1||v.getUint8(8)!==kind)throw Error(name+" has wrong XWSC01 version/kind");
 const comp=v.getUint8(9),rawSize=u64(v,14),size=u64(v,22),stored=b.slice(62,62+size);let raw;
 if(comp===0)raw=stored.slice();else if(comp===1){if(typeof DecompressionStream==="undefined")throw Error("browser lacks DecompressionStream");raw=new Uint8Array(await new Response(new Blob([stored]).stream().pipeThrough(new DecompressionStream("deflate"))).arrayBuffer())}else throw Error("unsupported compression");
 if(raw.length!==rawSize)throw Error(name+" size mismatch");
 const hash=new Uint8Array(await crypto.subtle.digest("SHA-256",raw));for(let i=0;i<32;i++)if(hash[i]!==b[30+i])throw Error(name+" SHA-256 mismatch");
 log("[PASS] "+name+" container verified","pass");return raw;
}
async function run(){
 $("log").textContent="";const rf=$("runtime").files[0],pf=$("payload").files[0];if(!rf||!pf){log("Select runtime.xwasm and payload.xpl first.","fail");return}
 try{
  const wasm=await unpack(await rf.arrayBuffer(),1,"runtime.xwasm"),pe=await unpack(await pf.arrayBuffer(),2,"payload.xpl");
  if(wasm[0]!==0||wasm[1]!==0x61||wasm[2]!==0x73||wasm[3]!==0x6d)throw Error("XWASM payload is not WASM");
  if(pe[0]!==0x4d||pe[1]!==0x5a)throw Error("XPL payload is not PE32");
  const mod=await WebAssembly.compile(wasm),env={};let memory;
  for(const i of WebAssembly.Module.imports(mod))if(i.module==="env"){if(i.kind==="memory"){memory=new WebAssembly.Memory({initial:1024,maximum:4096});env[i.name]=memory}else if(i.kind==="function")env[i.name]=()=>0}
  if(!memory)throw Error("runtime did not import memory");
  const ins=await WebAssembly.instantiate(mod,{env}),e=ins.exports,need=n=>{if(!e[n])throw Error("runtime export missing: "+n)};
  ["x86_get_runtime_version","xwasm_init","x86_load_pe","x86_get_loaded","x86_get_load_error","x86_run","x86_get_halted","x86_get_cpu_error"].forEach(need);
  if(e.x86_get_runtime_version()!==0x90000)throw Error("unexpected runtime version: "+hex(e.x86_get_runtime_version()));log("[PASS] runtime version 0x00090000","pass");
  if(e.xwasm_init()!==0)throw Error("xwasm_init failed");log("[PASS] init","pass");
  const view=new Uint8Array(memory.buffer),addr=0x100000;view.set(pe,addr);
  if(e.x86_load_pe(addr,pe.length)!==0)throw Error("PE load failed");
  if(e.x86_get_loaded()!==1||e.x86_get_load_error()!==0)throw Error("PE state invalid");log("[PASS] PE32 loaded","pass");
  const r=e.x86_run(2000);log("[INFO] CPU run="+r+" steps="+e.x86_get_steps()+" EIP="+hex(e.x86_get_eip())+" EAX="+hex(e.x86_get_eax())+" EFLAGS="+hex(e.x86_get_eflags()));
  if(e.x86_get_halted()!==1)throw Error("CPU did not halt");log("[PASS] CPU halted","pass");
  if(e.x86_get_cpu_error()!==0)throw Error("CPU error="+hex(e.x86_get_cpu_error()));log("[PASS] CPU error=0","pass");
  log("[PASS] XWASM CPU test complete","pass");
 }catch(err){log(String(err&&err.stack?err.stack:err),"fail")}
}
$("run").addEventListener("click",run);
})();