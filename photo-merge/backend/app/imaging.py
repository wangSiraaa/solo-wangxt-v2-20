"""Pillow 图像处理：归一化落盘（裁剪 / 限尺寸 / 压缩）、缩略图、感知哈希。

感知哈希采用经典 pHash（32x32 灰度 → DCT → 取左上 8x8 中频，按中位数二值化）。
不依赖 numpy，DCT 直接按定义计算，单张图片开销可忽略。
"""
from __future__ import annotations

import hashlib
import io
import math
import uuid
from typing import Optional

from PIL import Image

from . import config

# ---------------------------------------------------------------------------
# 感知哈希
# ---------------------------------------------------------------------------


def _dct_1d(rows: list[list[float]]) -> list[list[float]]:
    """对每行做 DCT-II（N=32）。返回等长二维表。"""
    n = len(rows[0])
    out: list[list[float]] = []
    for row in rows:
        coeffs = []
        for k in range(n):
            s = 0.0
            scale = math.sqrt(1 / n) if k == 0 else math.sqrt(2 / n)
            for i, x in enumerate(row):
                s += x * math.cos(math.pi * k * (2 * i + 1) / (2 * n))
            coeffs.append(scale * s)
        out.append(coeffs)
    return out


def _dct_2d(im: Image.Image) -> list[list[float]]:
    size = 32
    small = im.convert("L").resize((size, size), Image.LANCZOS)
    pixels = [
        [float(small.getpixel((x, y))) for x in range(size)]
        for y in range(size)
    ]
    horizontal = _dct_1d(pixels)
    # 转置后再做一次即完成列方向 DCT
    transposed = [list(col) for col in zip(*horizontal)]
    vertical = _dct_1d(transposed)
    return [list(col) for col in zip(*vertical)]


def _median(values: list[float]) -> float:
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def phash_hex(im: Image.Image) -> str:
    """返回 64bit pHash 的 16 位 hex 字符串。"""
    dct = _dct_2d(im)
    # 左上 8x8，跳过直流分量 (0,0)，取 63 个 + 用 (0,0) 占位凑 64
    block: list[float] = []
    for y in range(8):
        for x in range(8):
            block.append(dct[y][x])
    block[0] = block[1]  # 直流项不参与，复制一个中频值占位
    med = _median(block)
    bits = 0
    for i, v in enumerate(block):
        if v > med:
            bits |= 1 << (63 - i)
    return f"{bits:016x}"


def hamming_distance(hash_a: str, hash_b: str) -> int:
    return (int(hash_a, 16) ^ int(hash_b, 16)).bit_count()


# ---------------------------------------------------------------------------
# 文件处理
# ---------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _apply_crop(im: Image.Image, crop: Optional[dict]) -> Image.Image:
    """crop = {x, y, width, height}，坐标基于原图（前端按原图比例回传）。"""
    if not crop:
        return im
    w, h = im.size
    left = max(0, int(crop["x"] * w))
    top = max(0, int(crop["y"] * h))
    right = min(w, left + int(crop["width"] * w))
    bottom = min(h, top + int(crop["height"] * h))
    if right <= left or bottom <= top:
        return im
    return im.crop((left, top, right, bottom))


def process_upload(
    raw: bytes,
    crop: Optional[dict] = None,
) -> dict:
    """接收上传字节 → 裁剪 / 限尺寸 / JPEG 压缩 / 缩略图，返回索引所需全部信息。"""
    im = Image.open(io.BytesIO(raw))
    im.load()

    im = _apply_crop(im, crop)

    # 透明通道统一铺白底，保证 JPEG 输出稳定
    if im.mode in ("RGBA", "P", "LA"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    elif im.mode != "RGB":
        im = im.convert("RGB")

    # 限尺寸（长边不超 MAX_DIMENSION）
    im.thumbnail((config.MAX_DIMENSION, config.MAX_DIMENSION), Image.LANCZOS)

    token = uuid.uuid4().hex
    stored_name = f"{token}.jpg"
    thumb_name = f"{token}_thumb.jpg"

    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=config.JPEG_QUALITY, optimize=True)
    stored_bytes = buf.getvalue()

    thumb = im.copy()
    thumb.thumbnail((config.THUMB_SIZE, config.THUMB_SIZE), Image.LANCZOS)
    tbuf = io.BytesIO()
    thumb.save(tbuf, format="JPEG", quality=80, optimize=True)

    (config.ORIGINAL_DIR / stored_name).write_bytes(stored_bytes)
    (config.THUMB_DIR / thumb_name).write_bytes(tbuf.getvalue())

    return {
        "stored_name": stored_name,
        "thumb_name": thumb_name,
        "width": im.size[0],
        "height": im.size[1],
        "phash": phash_hex(im),
    }
