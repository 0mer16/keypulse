"""Minimal OpenRGB SDK client (standard library only).

Talks to OpenRGB's SDK server (start OpenRGB with --server, default port 6742)
and gives per-key control of the Mountain Everest 60 (or any OpenRGB device).

Uses SDK protocol version 0, which is the simplest wire format and is
supported by every OpenRGB server.
"""
import socket
import struct

MAGIC = b"ORGB"
REQUEST_CONTROLLER_COUNT = 0
REQUEST_CONTROLLER_DATA = 1
SET_CLIENT_NAME = 50
RGBCONTROLLER_UPDATELEDS = 1050
RGBCONTROLLER_SETCUSTOMMODE = 1100
NO_LED = 0xFFFFFFFF


class _Reader:
    def __init__(self, data):
        self.d, self.o = data, 0

    def take(self, fmt):
        v = struct.unpack_from("<" + fmt, self.d, self.o)
        self.o += struct.calcsize("<" + fmt)
        return v if len(v) > 1 else v[0]

    def string(self):
        n = self.take("H")
        s = self.d[self.o:self.o + n].rstrip(b"\x00").decode("utf-8", "replace")
        self.o += n
        return s


class Device:
    """One RGB device as reported by OpenRGB (protocol 0 layout)."""

    def __init__(self, index, data):
        r = _Reader(data)
        r.take("I")  # data size
        self.index = index
        self.type = r.take("i")
        self.name = r.string()
        self.description = r.string()
        self.version = r.string()
        self.serial = r.string()
        self.location = r.string()
        self.modes = []
        num_modes = r.take("H")
        self.active_mode = r.take("i")
        for _ in range(num_modes):
            name = r.string()
            r.take("i")            # value
            r.take("IIIII")        # flags, speed_min, speed_max, colors_min, colors_max
            r.take("III")          # speed, direction, color_mode
            n_colors = r.take("H")
            r.o += 4 * n_colors     # skip mode colours
            self.modes.append(name)
        self.zones = []
        for _ in range(r.take("H")):
            zname = r.string()
            r.take("i")            # zone type
            r.take("II")           # leds_min, leds_max
            count = r.take("I")
            matrix = None
            if r.take("H") > 0:
                h, w = r.take("II")
                cells = struct.unpack_from("<%dI" % (h * w), r.d, r.o)
                r.o += 4 * h * w
                matrix = [list(cells[y * w:(y + 1) * w]) for y in range(h)]
            self.zones.append({"name": zname, "count": count, "matrix": matrix})
        self.leds = []
        for _ in range(r.take("H")):
            self.leds.append(r.string())
            r.take("I")
        self.led_count = len(self.leds)

    @property
    def matrix(self):
        """Key grid: rows of LED indices (NO_LED where there is no key)."""
        for z in self.zones:
            if z["matrix"]:
                return z["matrix"]
        return [list(range(self.led_count))]


class OpenRGB:
    def __init__(self, host="127.0.0.1", port=6742, name="KeyPulse"):
        self.sock = socket.create_connection((host, port), timeout=5)
        self._send(0, SET_CLIENT_NAME, name.encode() + b"\x00")

    def _send(self, dev, pkt, payload=b""):
        self.sock.sendall(MAGIC + struct.pack("<III", dev, pkt, len(payload)) + payload)

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("OpenRGB closed the connection")
            buf += chunk
        return buf

    def _recv(self):
        hdr = self._recv_exact(16)
        if hdr[:4] != MAGIC:
            raise ConnectionError("bad reply from OpenRGB")
        dev, pkt, size = struct.unpack("<III", hdr[4:])
        return pkt, self._recv_exact(size)

    def devices(self):
        self._send(0, REQUEST_CONTROLLER_COUNT)
        _, data = self._recv()
        count = struct.unpack("<I", data)[0]
        out = []
        for i in range(count):
            self._send(i, REQUEST_CONTROLLER_DATA)
            _, data = self._recv()
            out.append(Device(i, data))
        return out

    def find(self, text="Everest"):
        for d in self.devices():
            if text.lower() in d.name.lower():
                return d
        raise LookupError(f"No OpenRGB device matching {text!r}")

    def direct_mode(self, dev):
        """Switch the device to live per-key control (nothing is saved to flash)."""
        self._send(dev.index, RGBCONTROLLER_SETCUSTOMMODE)

    def set_colors(self, dev, colors):
        """colors: list of (r, g, b) tuples, one per LED, 0-255 each."""
        body = struct.pack("<H", len(colors)) + b"".join(
            struct.pack("<BBBx", int(r) & 255, int(g) & 255, int(b) & 255) for r, g, b in colors)
        self._send(dev.index, RGBCONTROLLER_UPDATELEDS, struct.pack("<I", 4 + len(body)) + body)

    def close(self):
        self.sock.close()
