// XWASM X86 Runtime v0.1 browser bridge.
// The runtime stays standard WebAssembly; package files are supplied by the XWASM host.
(function(){
  function makeHost(pkg){
    const enc=new TextEncoder();
    const log=(level,ptr,len)=>{
      const m=pkg.memory;
      if(!m)return;
      const bytes=new Uint8Array(m.buffer,ptr,len);
      const s=new TextDecoder().decode(bytes);
      (level>=2?console.error:console.log)("[XWASM X86] "+s);
    };
    const resourceSize=(ptr,len)=>{const p=pkg.readString(ptr,len);const f=pkg.get(p);return f?f.size||f.byteLength:-1;};
    const resourceRead=(ptr,len,dst,dstLen,off)=>{const p=pkg.readString(ptr,len),f=pkg.get(p);if(!f)return -1;const b=pkg.bytes(f),n=Math.max(0,Math.min(dstLen,b.length-off));if(n>0)new Uint8Array(pkg.memory.buffer,dst,n).set(b.subarray(off,off+n));return n;};
    return {xwasm:{host:{log,resource_size:resourceSize,resource_read:resourceRead}}};
  }
  window.XWASM_X86_HOST={makeHost};
})();
