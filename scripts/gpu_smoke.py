#!/usr/bin/env python3
"""Execute a CUDA kernel through the driver API and verify device output."""
import ctypes as C
import json

cuda = C.CDLL("libcuda.so.1")
def call(name, *args):
    code = getattr(cuda, name)(*args)
    if code:
        message = C.c_char_p()
        cuda.cuGetErrorString(code, C.byref(message))
        raise RuntimeError(f"{name}: {code} {message.value!r}")

call("cuInit", 0)
device = C.c_int()
call("cuDeviceGet", C.byref(device), 0)
name = C.create_string_buffer(256)
call("cuDeviceGetName", name, 256, device)
version = C.c_int()
call("cuDriverGetVersion", C.byref(version))
context = C.c_void_p()
call("cuCtxCreate_v2", C.byref(context), 0, device)
address = C.c_uint64()
module = C.c_void_p()
try:
    call("cuMemAlloc_v2", C.byref(address), C.c_size_t(4))
    ptx = C.create_string_buffer(b""".version 7.0
.target sm_80
.address_size 64
.visible .entry write_answer(.param .u64 output) {
.reg .u64 %rd1;
.reg .u32 %r1;
ld.param.u64 %rd1, [output];
mov.u32 %r1, 42;
st.global.u32 [%rd1], %r1;
ret;
}
""")
    call("cuModuleLoadData", C.byref(module), ptx)
    function = C.c_void_p()
    call("cuModuleGetFunction", C.byref(function), module, b"write_answer")
    arguments = (C.c_void_p * 1)(C.addressof(address))
    call("cuLaunchKernel", function, 1, 1, 1, 1, 1, 1, 0, C.c_void_p(), arguments, C.c_void_p())
    call("cuCtxSynchronize")
    result = C.c_uint32()
    call("cuMemcpyDtoH_v2", C.byref(result), address, C.c_size_t(4))
    if result.value != 42:
        raise AssertionError(f"CUDA result {result.value} != 42")
    print(json.dumps({"status": "PASS", "gpu": name.value.decode(), "cuda_driver_api_version": version.value, "kernel_result": result.value}))
finally:
    if module.value:
        call("cuModuleUnload", module)
    if address.value:
        call("cuMemFree_v2", address)
    call("cuCtxDestroy_v2", context)
