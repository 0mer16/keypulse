"""Capture whatever Windows is playing (WASAPI loopback), using only ctypes + numpy.

    cap = Loopback()          # opens the default playback device
    samples = cap.read()      # mono float32 numpy array of everything since last read
    cap.close()
"""
import ctypes
import time
import uuid
from ctypes import POINTER, byref, c_uint32, c_uint64, c_void_p, wintypes

import numpy as np

ole32 = ctypes.OleDLL("ole32")

CLSCTX_ALL = 0x17
E_RENDER, E_MULTIMEDIA = 0, 1
SHAREMODE_SHARED = 0
STREAMFLAGS_LOOPBACK = 0x00020000
BUFFERFLAGS_SILENT = 0x2
WAVE_FORMAT_IEEE_FLOAT = 3
WAVE_FORMAT_EXTENSIBLE = 0xFFFE


def _guid(s):
    return (ctypes.c_byte * 16).from_buffer_copy(uuid.UUID(s).bytes_le)


CLSID_MMDeviceEnumerator = _guid("BCDE0395-E52F-467C-8E3D-C4579291692E")
IID_IMMDeviceEnumerator = _guid("A95664D2-9614-4F35-A746-DE8DB63617E6")
IID_IAudioClient = _guid("1CB9AD4C-DBFA-4C32-B178-C2F568A703B2")
IID_IAudioCaptureClient = _guid("C8ADBD64-E71E-48A0-A4DE-185C395CD317")
SUBTYPE_FLOAT = uuid.UUID("00000003-0000-0010-8000-00AA00389B71").bytes_le


class WAVEFORMATEX(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("wFormatTag", wintypes.WORD), ("nChannels", wintypes.WORD),
                ("nSamplesPerSec", wintypes.DWORD), ("nAvgBytesPerSec", wintypes.DWORD),
                ("nBlockAlign", wintypes.WORD), ("wBitsPerSample", wintypes.WORD),
                ("cbSize", wintypes.WORD)]


class WAVEFORMATEXTENSIBLE(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("Format", WAVEFORMATEX), ("wValidBitsPerSample", wintypes.WORD),
                ("dwChannelMask", wintypes.DWORD), ("SubFormat", ctypes.c_byte * 16)]


def _method(obj, index, *argtypes):
    """Bind COM vtable slot `index` of interface pointer `obj`."""
    vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
    proto = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)
    fn = proto(vtbl[index])
    return lambda *args: fn(obj, *args)


def _device_id(device):
    """IMMDevice::GetId - a string that identifies the playback device."""
    p = ctypes.c_wchar_p()
    _method(device, 5, POINTER(ctypes.c_wchar_p))(byref(p))
    s = p.value
    ole32.CoTaskMemFree(p)
    return s


class DeviceChanged(OSError):
    """Windows switched its default playback device; the capture must be reopened."""


def _release(obj):
    if obj:
        ctypes.WINFUNCTYPE(c_uint32, c_void_p)(
            ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents[2])(obj)


class Loopback:
    def __init__(self):
        try:
            ole32.CoInitializeEx(None, 0)
        except OSError:
            pass  # already initialised on this thread
        self._enum = c_void_p()
        ole32.CoCreateInstance(byref(CLSID_MMDeviceEnumerator), None, CLSCTX_ALL,
                               byref(IID_IMMDeviceEnumerator), byref(self._enum))
        self._device = c_void_p()
        _method(self._enum, 4, ctypes.c_int, ctypes.c_int, POINTER(c_void_p))(
            E_RENDER, E_MULTIMEDIA, byref(self._device))
        self.device_id = _device_id(self._device)
        self._next_check = time.monotonic() + 2.0
        self._client = c_void_p()
        _method(self._device, 3, c_void_p, wintypes.DWORD, c_void_p, POINTER(c_void_p))(
            byref(IID_IAudioClient), CLSCTX_ALL, None, byref(self._client))

        fmt_ptr = POINTER(WAVEFORMATEX)()
        _method(self._client, 8, POINTER(POINTER(WAVEFORMATEX)))(byref(fmt_ptr))
        fmt = fmt_ptr.contents
        self.rate = fmt.nSamplesPerSec
        self.channels = fmt.nChannels
        self._block = fmt.nBlockAlign
        bits = fmt.wBitsPerSample
        is_float = fmt.wFormatTag == WAVE_FORMAT_IEEE_FLOAT or (
            fmt.wFormatTag == WAVE_FORMAT_EXTENSIBLE and
            bytes(ctypes.cast(fmt_ptr, POINTER(WAVEFORMATEXTENSIBLE)).contents.SubFormat) == SUBTYPE_FLOAT)
        if is_float and bits == 32:
            self._dtype, self._scale = np.float32, 1.0
        elif bits == 16:
            self._dtype, self._scale = np.int16, 1 / 32768
        elif bits == 32:
            self._dtype, self._scale = np.int32, 1 / 2147483648
        else:
            raise RuntimeError(f"Unsupported audio format: {bits}-bit tag {fmt.wFormatTag}")

        # 1 second shared-mode buffer, loopback of the render endpoint
        _method(self._client, 3, ctypes.c_int, wintypes.DWORD, ctypes.c_longlong,
                ctypes.c_longlong, POINTER(WAVEFORMATEX), c_void_p)(
            SHAREMODE_SHARED, STREAMFLAGS_LOOPBACK, 10_000_000, 0, fmt_ptr, None)
        ole32.CoTaskMemFree(fmt_ptr)

        self._capture = c_void_p()
        _method(self._client, 14, c_void_p, POINTER(c_void_p))(
            byref(IID_IAudioCaptureClient), byref(self._capture))
        self._next_size = _method(self._capture, 5, POINTER(c_uint32))
        self._get = _method(self._capture, 3, POINTER(c_void_p), POINTER(c_uint32),
                            POINTER(wintypes.DWORD), POINTER(c_uint64), POINTER(c_uint64))
        self._free = _method(self._capture, 4, c_uint32)
        _method(self._client, 10)()  # Start

    def _check_default_device(self):
        """Every 2 s, make sure we're still capturing the device Windows is playing through."""
        now = time.monotonic()
        if now < self._next_check:
            return
        self._next_check = now + 2.0
        dev = c_void_p()
        try:
            _method(self._enum, 4, ctypes.c_int, ctypes.c_int, POINTER(c_void_p))(
                E_RENDER, E_MULTIMEDIA, byref(dev))
            current = _device_id(dev)
        except OSError:
            return            # no playback device at all right now; keep what we have
        finally:
            _release(dev)
        if current != self.device_id:
            raise DeviceChanged("default playback device changed")

    def read(self):
        """Return all audio captured since the last call as a mono float32 array.

        Raises OSError (DeviceChanged) when the playback device changes; reopen a new Loopback then."""
        self._check_default_device()
        chunks = []
        size = c_uint32()
        self._next_size(byref(size))
        while size.value:
            data, frames, flags = c_void_p(), c_uint32(), wintypes.DWORD()
            self._get(byref(data), byref(frames), byref(flags), None, None)
            n = frames.value
            if flags.value & BUFFERFLAGS_SILENT or not data.value:
                chunks.append(np.zeros(n, np.float32))
            else:
                raw = np.frombuffer(ctypes.string_at(data.value, n * self._block), self._dtype)
                chunks.append(raw.reshape(n, self.channels).mean(axis=1).astype(np.float32) * self._scale)
            self._free(n)
            self._next_size(byref(size))
        return np.concatenate(chunks) if chunks else np.zeros(0, np.float32)

    def close(self):
        try:
            _method(self._client, 11)()  # Stop
        except OSError:
            pass
        for obj in (self._capture, self._client, self._device, self._enum):
            _release(obj)
