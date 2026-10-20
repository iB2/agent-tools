"""Pack any bytes into the RGB pixels of a PNG, and back.

Layout: a 4-byte big-endian length, then the bytes, then zero padding, written row by row
into 8-bit RGB pixels of a WIDTH-wide image. Chat hosts that inline only images can carry
a deck or its audio this way; the browser reads the pixels back with canvas getImageData.
"""
import math
import struct
import zlib

WIDTH = 2048
SIG = b"\x89PNG\r\n\x1a\n"


def _chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)


def pack(data, width=WIDTH):
    payload = struct.pack(">I", len(data)) + data
    w = min(width, max(1, math.ceil(len(payload) / 3)))
    h = math.ceil(len(payload) / 3 / w)
    payload += b"\0" * (w * h * 3 - len(payload))
    rows = b"".join(b"\x00" + payload[y * w * 3:(y + 1) * w * 3] for y in range(h))
    return SIG + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + _chunk(b"IDAT", zlib.compress(rows, 9)) + _chunk(b"IEND", b"")


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def pixels(png):
    """Decode an 8-bit RGB or RGBA non-interlaced PNG to its RGB bytes."""
    if png[:8] != SIG:
        raise ValueError("not a PNG")
    i, idat, w = 8, b"", None
    while i < len(png):
        n, t = struct.unpack(">I4s", png[i:i + 8])
        d = png[i + 8:i + 8 + n]
        if t == b"IHDR":
            w, h, depth, ctype, _, _, inter = struct.unpack(">IIBBBBB", d)
            if depth != 8 or ctype not in (2, 6) or inter:
                raise ValueError("only 8-bit RGB or RGBA, non-interlaced")
            bpp = 3 if ctype == 2 else 4
        elif t == b"IDAT":
            idat += d
        i += 12 + n
    raw, stride = zlib.decompress(idat), w * bpp
    out, prev = bytearray(), bytearray(stride)
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for x in range(stride) if f else ():
            a = line[x - bpp] if x >= bpp else 0
            b, c = prev[x], (prev[x - bpp] if x >= bpp else 0)
            line[x] = (line[x] + (0, a, b, (a + b) // 2, _paeth(a, b, c))[f]) & 0xFF
        if bpp == 4:
            rgb = bytearray(line)
            del rgb[3::4]
            out += rgb
        else:
            out += line
        prev = line
    return bytes(out)


def unpack(png):
    rgb = pixels(png)
    n = struct.unpack(">I", rgb[:4])[0]
    if n > len(rgb) - 4:
        raise ValueError("length header is larger than the image")
    return rgb[4:4 + n]
