"""Deterministic PWA icon PNGs without external graphics dependencies."""
from functools import lru_cache
import struct
import zlib


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))


@lru_cache(maxsize=2)
def icon_png(size: int) -> bytes:
    """Return an installable opaque RGB icon (192 or 512px) with a rising chart."""
    if size not in (192, 512):
        raise ValueError("Unsupported icon dimensions")
    bg = (16, 24, 39)
    green = (53, 212, 165)
    white = (236, 245, 250)
    vertices = [(0.15, .68), (.31, .52), (.46, .60), (.63, .31), (.84, .41)]
    rows = []
    for y in range(size):
        scanline = bytearray(b"\0")
        for x in range(size):
            xx, yy = x / size, y / size
            color = bg
            for (ax, ay), (bx, by) in zip(vertices, vertices[1:]):
                dx, dy = bx - ax, by - ay
                t = max(0., min(1., ((xx - ax) * dx + (yy - ay) * dy) / (dx * dx + dy * dy)))
                if ((xx - ax - t * dx) ** 2 + (yy - ay - t * dy) ** 2) < .009 ** 2:
                    color = green
                    break
            if (xx - .63) ** 2 + (yy - .31) ** 2 < .022 ** 2:
                color = white
            scanline.extend(color)
        rows.append(bytes(scanline))
    raw = zlib.compress(b"".join(rows), 9)
    return (b"\x89PNG\r\n\x1a\n" +
            _chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) +
            _chunk(b"IDAT", raw) + _chunk(b"IEND", b""))
