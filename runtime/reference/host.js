/* XWASM reference browser host ABI v1.
 *
 * This is deliberately small. It is a host convention around standard
 * WebAssembly, not a replacement WebAssembly runtime.
 */
(function () {
  "use strict";

  const ABI = "xwasm.host/1";

  function normalizePath(path) {
    path = String(path || "").replace(/\\/g, "/").replace(/^\/+/, "");
    const parts = [];
    for (const part of path.split("/")) {
      if (!part || part === ".") continue;
      if (part === "..") throw new Error("resource path escapes package root");
      parts.push(part);
    }
    return parts.join("/");
  }

  function makeHost(options) {
    const memoryRef = { value: options.memory || null };
    const readResource = options.readResource;
    const log = options.log || ((level, message) => console.log("[XWASM]", level, message));
    const timeOrigin = performance.now();

    function memory() {
      if (!memoryRef.value) throw new Error("XWASM memory is not available");
      return new Uint8Array(memoryRef.value.buffer);
    }

    function readString(ptr, len) {
      return new TextDecoder().decode(memory().subarray(ptr, ptr + len));
    }

    function writeBytes(ptr, bytes) {
      const mem = memory();
      if (ptr < 0 || ptr + bytes.length > mem.length) {
        throw new RangeError("XWASM host write is outside linear memory");
      }
      mem.set(bytes, ptr);
      return bytes.length;
    }

    const handles = new Map();
    let nextHandle = 1;

    async function openResource(path) {
      const key = normalizePath(path);
      const bytes = new Uint8Array(await readResource(key));
      const handle = nextHandle++;
      handles.set(handle, bytes);
      return handle;
    }

    return {
      memoryRef,

      imports: {
        log(level, ptr, len) {
          log(level, readString(ptr, len));
        },

        time_ms() {
          return Math.floor(performance.now() - timeOrigin);
        },

        resource_size(pathPtr, pathLen) {
          // This ABI call is synchronous by design only for runtimes that
          // already cache/index resource sizes. The reference host returns -1
          // when a size index is unavailable.
          if (typeof options.resourceSize === "function") {
            return options.resourceSize(normalizePath(readString(pathPtr, pathLen)));
          }
          return -1;
        },

        resource_open_async(pathPtr, pathLen) {
          const path = normalizePath(readString(pathPtr, pathLen));
          const promise = openResource(path);
          const token = nextHandle++;
          handles.set(token, promise);
          return token;
        },

        resource_read(handle, dstPtr, dstLen, offset) {
          const value = handles.get(handle);
          if (!(value instanceof Uint8Array)) return -1;
          const start = Math.max(0, offset | 0);
          const count = Math.min(Math.max(0, dstLen | 0), value.length - start);
          if (count <= 0) return 0;
          return writeBytes(dstPtr, value.subarray(start, start + count));
        },

        resource_close(handle) {
          handles.delete(handle);
        },

        exit(code) {
          if (typeof options.onExit === "function") options.onExit(code | 0);
        }
      }
    };
  }

  window.XWASMHost = {
    ABI,
    makeHost
  };
})();
