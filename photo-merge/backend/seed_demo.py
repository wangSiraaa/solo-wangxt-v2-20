"""生成演示数据：程序化绘制 4 个场景的照片及近重复变体。

覆盖情况：
- 精确重复（字节一致）、重压缩、轻微裁剪、轻微缩放/调色 —— 应当产生候选并可归并；
- 同场景不同照片（同一片湖，前景主体不同）—— 会产生近距离候选，留给人工判为误判；
- 同内容但授权范围不同 —— 候选存在，但归并必须被后端拒绝；
- 完全不同的场景 —— 不应产生候选。
另外创建 3 个引用项目与若干引用，便于演示“归并后引用仍可追踪”。
"""
from __future__ import annotations

import io
import json
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

BASE = "http://127.0.0.1:8000"
W, H = 900, 600


# ---------------------------------------------------------------------------
# 场景绘制
# ---------------------------------------------------------------------------


def _canvas(top, bottom):
    im = Image.new("RGB", (W, H))
    px = im.load()
    for y in range(H):
        t = y / H
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        for x in range(W):
            px[x, y] = (r, g, b)
    return im


def scene_sunset(boat: bool = True) -> Image.Image:
    """湖边日落：渐变天空 + 水面 + 太阳；boat 控制前景是否有船（同场景不同照片）。"""
    im = _canvas((255, 150, 60), (40, 50, 110))
    d = ImageDraw.Draw(im)
    # 水面分界
    d.rectangle([0, 380, W, H], fill=(30, 45, 90))
    # 太阳
    d.ellipse([380, 120, 520, 260], fill=(255, 225, 150))
    for i in range(6):
        d.line([0, 410 + i * 32, W, 410 + i * 32], fill=(70, 90, 150), width=2)
    if boat:
        d.polygon([(180, 360), (300, 360), (260, 395), (210, 395)], fill=(60, 30, 20))
        d.line([240, 360, 240, 290], fill=(40, 20, 10), width=4)
        d.polygon([(240, 290), (240, 350), (285, 350)], fill=(230, 220, 200))
    else:
        # 同一片湖、同一时刻，但前景换成礁石群 —— 构图位置与船接近，
        # pHash 距离落在阈值边缘，实际是另一张照片（典型的“看起来很近”的误判候选）
        d.polygon([(185, 395), (215, 352), (248, 395)], fill=(52, 48, 56))
        d.polygon([(240, 395), (278, 348), (308, 395)], fill=(42, 38, 48))
        d.polygon([(208, 395), (242, 366), (268, 395)], fill=(68, 60, 64))
    return im


def scene_skyline(variant: int = 0) -> Image.Image:
    """城市夜景天际线，variant=1 时多一栋楼（同场景不同照片）。"""
    im = _canvas((10, 12, 40), (30, 30, 70))
    d = ImageDraw.Draw(im)
    buildings = [(40, 300, 130), (160, 220, 260), (300, 320, 400),
                 (440, 180, 560), (600, 280, 700), (740, 240, 860)]
    if variant == 1:
        buildings.insert(3, (370, 250, 430))
    for x0, top, x1 in buildings:
        d.rectangle([x0, top, x1, H], fill=(20, 22, 45))
        for wy in range(top + 20, H - 20, 34):
            for wx in range(x0 + 12, x1 - 12, 26):
                if (wx + wy) % 3 != 0:
                    d.rectangle([wx, wy, wx + 10, wy + 14], fill=(250, 220, 120))
    d.rectangle([0, 470, W, H], fill=(15, 15, 30))
    return im


def scene_portrait(shirt: tuple = (180, 40, 40)) -> Image.Image:
    """棚拍人像剪影：shirt 换色构成不同授权/不同成片。"""
    im = Image.new("RGB", (W, H), (235, 232, 225))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 460, W, H], fill=(200, 195, 185))
    d.ellipse([360, 120, 540, 300], fill=(225, 190, 160))       # 头
    d.ellipse([310, 290, 590, 520], fill=shirt)                 # 上衣
    d.arc([360, 120, 540, 300], 180, 360, fill=(70, 50, 40), width=18)  # 头发
    d.ellipse([405, 205, 435, 225], fill=(40, 30, 25))
    d.ellipse([465, 205, 495, 225], fill=(40, 30, 25))
    d.polygon([(450, 230), (420, 265), (480, 265)], fill=(190, 150, 130))
    return im


def scene_forest() -> Image.Image:
    """完全不相似的对照场景。"""
    im = _canvas((60, 110, 60), (20, 50, 25))
    d = ImageDraw.Draw(im)
    for x in range(0, W, 60):
        d.rectangle([x + 20, 80, x + 45, H], fill=(70, 45, 25))
        d.ellipse([x - 30, 20, x + 90, 180], fill=(35, 90, 40))
    return im


# ---------------------------------------------------------------------------
# 近重复变换（模拟摄影师反复上传）
# ---------------------------------------------------------------------------


def recompress(im: Image.Image, quality: int = 45) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def recolor(im: Image.Image) -> Image.Image:
    return ImageEnhance.Color(im).enhance(1.18)


def slight_crop(im: Image.Image) -> Image.Image:
    w, h = im.size
    return im.crop((40, 30, w - 30, h - 20))


def slight_resize(im: Image.Image) -> Image.Image:
    return im.resize((820, 547), Image.LANCZOS).resize((W, H), Image.LANCZOS)


def blur(im: Image.Image) -> Image.Image:
    return im.filter(ImageFilter.GaussianBlur(1.2))


# ---------------------------------------------------------------------------
# 通过 API 上传
# ---------------------------------------------------------------------------


def post_photo(filename, im_or_bytes, photographer, license_scope, caption,
               crop=None, quality=92):
    if isinstance(im_or_bytes, bytes):
        data = im_or_bytes
    else:
        buf = io.BytesIO()
        im_or_bytes.save(buf, format="JPEG", quality=quality)
        data = buf.getvalue()

    boundary = "----demoform"
    parts = []

    def add_field(name, value):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())

    add_field("photographer", photographer)
    add_field("license_scope", license_scope)
    add_field("caption", caption)
    if crop:
        add_field("crop", json.dumps(crop))
    head = (
        f"--{boundary}\r\n"
        f"Content-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    body = b"".join(parts) + head + data + tail
    req = urllib.request.Request(
        f"{BASE}/api/photos",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def post_json(path, payload):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main():
    sunset = scene_sunset(boat=True)
    sunset_other = scene_sunset(boat=False)
    city = scene_skyline(0)
    city_other = scene_skyline(1)
    portrait = scene_portrait()
    forest = scene_forest()

    uploaded = []

    # 场景一：湖边日落 —— 多张近重复（精确重复 / 重压缩 / 调色 / 裁剪 / 缩放）
    uploaded.append(post_photo(
        "sunset_01_master.jpg", sunset, "林溪", "editorial", "湖边日落主选片"))
    buf = io.BytesIO(); sunset.save(buf, "JPEG", quality=92)
    uploaded.append(post_photo(
        "sunset_02_same_bytes.jpg", buf.getvalue(), "林溪", "editorial",
        "相机直出重复上传（与01字节一致）"))
    uploaded.append(post_photo(
        "sunset_03_recompress.jpg", recompress(sunset, 42), "林溪", "editorial",
        "微信转发后的重压缩版本"))
    uploaded.append(post_photo(
        "sunset_04_recolor.jpg", recolor(sunset), "林溪", "editorial",
        "套过暖色滤镜的版本"))
    uploaded.append(post_photo(
        "sunset_05_cropped.jpg", sunset, "林溪", "editorial",
        "上传时手工裁掉边缘（演示上传裁剪管线）",
        crop={"x": 0.05, "y": 0.05, "width": 0.88, "height": 0.9}))
    uploaded.append(post_photo(
        "sunset_06_resized.jpg", slight_resize(sunset), "林溪", "editorial",
        "缩放过又拉大的版本"))
    # 同一场景的另一张照片（礁石前景）—— 典型误判候选
    uploaded.append(post_photo(
        "sunset_07_other_photo.jpg", sunset_other, "林溪", "editorial",
        "同一时刻同一场景，但前景是礁石——另一张照片，应判误判"))

    # 场景二：城市夜景
    uploaded.append(post_photo(
        "skyline_01.jpg", city, "高远", "commercial", "城市夜景全景"))
    uploaded.append(post_photo(
        "skyline_02_recompress.jpg", recompress(city, 50), "高远", "commercial",
        "客户邮件里回传的压缩版"))
    uploaded.append(post_photo(
        "skyline_03_blur.jpg", blur(city), "高远", "commercial", "轻微失焦版本"))
    uploaded.append(post_photo(
        "skyline_04_different_frame.jpg", city_other, "高远", "commercial",
        "同机位另一张（多一栋楼入画）——不同照片，应判误判"))

    # 场景三：棚拍人像 —— 内容一致但授权范围不同，禁止归并
    uploaded.append(post_photo(
        "portrait_01_editorial.jpg", portrait, "周白", "editorial",
        "棚拍人像（仅编辑类授权）"))
    uploaded.append(post_photo(
        "portrait_02_recompress.jpg", recompress(portrait, 55), "周白", "commercial",
        "同片输出但拿到的是商业授权——授权范围不同，禁止直接归并"))

    # 对照：完全不同场景
    uploaded.append(post_photo(
        "forest_01.jpg", forest, "林溪", "editorial", "森林公路（对照组）"))

    # 项目与引用
    p1 = post_json("/api/projects", {"code": "MAG-2026-09", "name": "9月刊·风光专题"})
    p2 = post_json("/api/projects", {"code": "ADS-ACME", "name": "Acme 城市品牌广告"})
    p3 = post_json("/api/projects", {"code": "BOOK-PORTRAIT", "name": "年度人像画册"})

    by_cap = {u["caption"]: u for u in uploaded}
    post_json("/api/refs", {"project_id": p1["id"],
              "photo_id": by_cap["湖边日落主选片"]["id"], "usage": "跨页大图"})
    post_json("/api/refs", {"project_id": p1["id"],
              "photo_id": by_cap["套过暖色滤镜的版本"]["id"], "usage": "目录缩略图"})
    post_json("/api/refs", {"project_id": p2["id"],
              "photo_id": by_cap["城市夜景全景"]["id"], "usage": "户外灯箱"})
    post_json("/api/refs", {"project_id": p3["id"],
              "photo_id": by_cap["棚拍人像（仅编辑类授权）"]["id"], "usage": "章节扉页"})

    print(f"已生成 {len(uploaded)} 张照片、{3} 个项目与 4 条引用")
    print("提示：先在「候选审查」里处理 sunset_07 / skyline_04 两个误判候选，")
    print("     再尝试把两张人像归并（后端会以授权范围不一致拒绝）。")


if __name__ == "__main__":
    main()
