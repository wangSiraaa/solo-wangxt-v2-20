"""感知哈希：aHash / dHash / pHash（64 位），用 Pillow + numpy 实现。

pHash 对缩放、压缩、轻微裁剪鲁棒，用于发现"看起来像"的候选；
候选只进入人工审查队列，系统不做任何自动删除。
"""
from io import BytesIO

import numpy as np
from PIL import Image

HASH_SIZE = 8


def _to_bits(arr: np.ndarray) -> int:
    bits = 0
    for v in arr.flatten():
        bits = (bits << 1) | int(bool(v))
    return bits


def ahash(img: Image.Image) -> int:
    g = img.convert("L").resize((HASH_SIZE, HASH_SIZE), Image.LANCZOS)
    a = np.asarray(g, dtype=np.float64)
    return _to_bits(a > a.mean())


def dhash(img: Image.Image) -> int:
    g = img.convert("L").resize((HASH_SIZE + 1, HASH_SIZE), Image.LANCZOS)
    a = np.asarray(g, dtype=np.float64)
    return _to_bits(a[:, 1:] > a[:, :-1])


def _dct_matrix(n: int) -> np.ndarray:
    """DCT-II 变换矩阵。"""
    m = np.zeros((n, n))
    for k in range(n):
        alpha = np.sqrt(1.0 / n) if k == 0 else np.sqrt(2.0 / n)
        for i in range(n):
            m[k, i] = alpha * np.cos(np.pi * (2 * i + 1) * k / (2 * n))
    return m


_DCT32 = _dct_matrix(32)


def phash(img: Image.Image) -> int:
    g = img.convert("L").resize((32, 32), Image.LANCZOS)
    a = np.asarray(g, dtype=np.float64)
    dct = _DCT32 @ a @ _DCT32.T
    low = dct[:HASH_SIZE, :HASH_SIZE]
    # 去掉直流分量后取中位数比较
    med = np.median(low.flatten()[1:])
    return _to_bits(low > med)


def compute_hashes(data: bytes) -> dict:
    img = Image.open(BytesIO(data))
    return {
        "ahash": f"{ahash(img):016x}",
        "dhash": f"{dhash(img):016x}",
        "phash": f"{phash(img):016x}",
    }


def hamming(hex_a: str, hex_b: str) -> int:
    return bin(int(hex_a, 16) ^ int(hex_b, 16)).count("1")
