"""Combine P4 PBM files into one scaled PNG contact sheet (CPython, stdlib only).

    python3 tools/pbm2png.py out.png a.pbm b.pbm ...

Expects binary P4 files without header comments (as written by preview.py),
all the same size.
"""
import struct
import sys
import zlib

SCALE, PAD = 3, 12
INK, PAPER, BG = (20, 20, 20), (236, 234, 226), (150, 150, 150)


def read_pbm(path):
    data = open(path, "rb").read()
    parts = data.split(b"\n", 2)
    w, h = map(int, parts[1].split())
    raw, rb = parts[2], (w + 7) // 8
    return w, h, [[(raw[y * rb + x // 8] >> (7 - x % 8)) & 1 for x in range(w)] for y in range(h)]


def main(out, paths):
    imgs = [read_pbm(p) for p in paths]
    cols = 2
    w, h = imgs[0][0] * SCALE, imgs[0][1] * SCALE
    rows = (len(imgs) + cols - 1) // cols
    W, H = cols * (w + PAD) + PAD, rows * (h + PAD) + PAD
    canvas = [[BG] * W for _ in range(H)]
    for i, (iw, ih, px) in enumerate(imgs):
        ox, oy = PAD + (i % cols) * (w + PAD), PAD + (i // cols) * (h + PAD)
        for y in range(ih * SCALE):
            row = px[y // SCALE]
            line = canvas[oy + y]
            for x in range(iw * SCALE):
                line[ox + x] = INK if row[x // SCALE] else PAPER
    raw = b"".join(b"\x00" + bytes(c for p in line for c in p) for line in canvas)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    open(out, "wb").write(png)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
