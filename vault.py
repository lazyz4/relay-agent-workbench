"""Optional Windows DPAPI persistence; decryption requires this Windows user."""
import ctypes
from ctypes import wintypes
import json
import os
from functools import lru_cache


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def transform(data, decrypt=False):
    if os.name != 'nt':
        raise ValueError('加密保存仅支持 Windows；可使用仅内存配置')
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    library = ctypes.WinDLL('crypt32', use_last_error=True)
    function = library.CryptUnprotectData if decrypt else library.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        code=ctypes.get_last_error()
        raise ValueError(f'当前 Windows 会话不能使用加密存储（错误 {code}）。请取消加密记住，使用内存配置；或在 Windows 中直接启动服务。')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


def save(path, value):
    encrypted = transform(json.dumps(value).encode('utf-8'))
    path.parent.mkdir(exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(encrypted)
    temporary.replace(path)


def load(path):
    return json.loads(transform(path.read_bytes(), decrypt=True).decode('utf-8'))


@lru_cache(maxsize=1)
def available():
    try:
        return transform(transform(b'relay-check'),decrypt=True)==b'relay-check'
    except ValueError:
        return False
