"""Минимальная запись PSD: RGB 8 бит, слои RGBA без сжатия, имена в юникоде. Без сторонних библиотек.

  write_psd(path, [(имя, PIL.Image RGBA, видим), ...])  — первый в списке — нижний слой
"""
import struct
from PIL import Image


def _pascal(name, pad):
    raw = name.encode("ascii", "replace")[:255]
    s = bytes([len(raw)]) + raw
    return s + b"\0" * (-len(s) % pad)


def _unicode_block(name):
    data = struct.pack(">I", len(name)) + name.encode("utf-16-be")
    data += b"\0" * (-len(data) % 4)
    return b"8BIMluni" + struct.pack(">I", len(data)) + data


def _planes(im):
    r, g, b, a = im.split()
    return {-1: a.tobytes(), 0: r.tobytes(), 1: g.tobytes(), 2: b.tobytes()}


def write_psd(path, layers):
    w, h = layers[0][1].size
    records, pixels = b"", b""
    for name, im, visible in layers:
        planes = _planes(im.convert("RGBA"))
        rec = struct.pack(">iiiiH", 0, 0, h, w, 4)
        for cid in (-1, 0, 1, 2):
            rec += struct.pack(">hI", cid, 2 + len(planes[cid]))
            pixels += struct.pack(">H", 0) + planes[cid]
        rec += b"8BIMnorm" + struct.pack(">BBBB", 255, 0, 0 if visible else 2, 0)
        extra = struct.pack(">II", 0, 0) + _pascal(f"layer{len(records)}", 4) + _unicode_block(name)
        records += rec + struct.pack(">I", len(extra)) + extra
    info = struct.pack(">h", -len(layers)) + records + pixels  # минус: альфа первого канала — прозрачность
    info += b"\0" * (len(info) % 2)
    layer_mask = struct.pack(">I", len(info)) + info + struct.pack(">I", 0)

    merged = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for _, im, visible in layers:
        if visible:
            merged = Image.alpha_composite(merged, im.convert("RGBA"))
    r, g, b, a = merged.split()

    with open(path, "wb") as f:
        f.write(b"8BPS" + struct.pack(">H6xHIIHH", 1, 4, h, w, 8, 3))
        f.write(struct.pack(">I", 0))  # цветовой режим
        f.write(struct.pack(">I", 0))  # ресурсы
        f.write(struct.pack(">I", len(layer_mask)) + layer_mask)
        f.write(struct.pack(">H", 0) + r.tobytes() + g.tobytes() + b.tobytes() + a.tobytes())
