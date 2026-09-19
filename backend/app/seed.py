"""生成演示数据：

- sunset 系列：原图 / 裁剪版 / 高压缩版 → 真重复，应被确认并归并
- sunset_alt：同场景不同照片（太阳位置、云、鸟不同）→ 哈希可能接近，属误判样例
- sunset_agency：与 sunset 原图几乎相同但授权范围不同 → 演示"不同授权不允许合并"
- studio 系列：原图 + 裁剪版
- 两张互不相关的照片
并预置部分项目引用。运行：python -m app.seed
"""
import os
import random
import shutil
from io import BytesIO

from PIL import Image, ImageDraw

from . import models, services
from .config import STORAGE_DIR
from .database import Base, SessionLocal, engine
from .hashing import compute_hashes

W, H = 640, 420


def draw_sunset(sun_x=430, sun_y=130, clouds=((90, 90, 150), (300, 60, 200)), birds=()) -> Image.Image:
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):  # 天空渐变
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(250 - 120 * t), int(150 - 60 * t), int(90 + 60 * t)))
    d.ellipse([sun_x - 45, sun_y - 45, sun_x + 45, sun_y + 45], fill=(255, 214, 120))  # 太阳
    for cx, cy, cw in clouds:  # 云
        d.ellipse([cx, cy, cx + cw, cy + 34], fill=(245, 230, 225))
    d.polygon([(0, H), (180, 250), (360, H)], fill=(70, 60, 90))  # 山
    d.polygon([(260, H), (470, 280), (W, H)], fill=(55, 50, 80))
    d.rectangle([0, H - 40, W, H], fill=(35, 45, 70))  # 海面
    for bx, by in birds:  # 飞鸟
        d.arc([bx - 12, by - 8, bx, by + 8], 200, 340, fill=(30, 30, 40), width=2)
        d.arc([bx, by - 8, bx + 12, by + 8], 200, 340, fill=(30, 30, 40), width=2)
    return img


def draw_studio(mug_x=250, bg=(232, 232, 238)) -> Image.Image:
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 300, W, H], fill=(200, 195, 190))  # 桌面
    d.rounded_rectangle([mug_x, 170, mug_x + 140, 320], 18, fill=(180, 40, 50))  # 杯子
    d.arc([mug_x + 130, 210, mug_x + 190, 280], 270, 90, fill=(180, 40, 50), width=16)
    d.ellipse([80, 230, 170, 320], fill=(60, 130, 90))  # 绿植
    d.rectangle([115, 300, 135, 330], fill=(120, 90, 60))
    return img


def draw_portrait() -> Image.Image:
    img = Image.new("RGB", (W, H), (40, 60, 95))
    d = ImageDraw.Draw(img)
    d.ellipse([260, 90, 380, 230], fill=(235, 200, 170))
    d.rectangle([240, 230, 400, 420], fill=(90, 30, 40))
    return img


def draw_night() -> Image.Image:
    random.seed(7)
    img = Image.new("RGB", (W, H), (12, 16, 38))
    d = ImageDraw.Draw(img)
    for _ in range(120):
        x, y = random.randint(0, W - 1), random.randint(0, 260)
        d.point((x, y), fill=(255, 255, 255))
    d.ellipse([500, 40, 580, 120], fill=(230, 230, 210))
    d.rectangle([0, 300, W, H], fill=(8, 10, 20))
    for bx in range(0, W, 70):
        d.rectangle([bx, 240, bx + 40, 300], fill=(20, 24, 44))
    return img


def jpg_bytes(img: Image.Image, quality=90) -> bytes:
    buf = BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def save_photo(db, img_bytes, filename, photographer, license_scope, refs=()):
    img = Image.open(BytesIO(img_bytes))
    stored = f"seed_{filename}"
    with open(os.path.join(STORAGE_DIR, stored), "wb") as f:
        f.write(img_bytes)
    photo = models.Photo(
        original_filename=filename,
        stored_filename=stored,
        photographer=photographer,
        license_scope=license_scope,
        width=img.width,
        height=img.height,
        file_size=len(img_bytes),
        status="active",
        **compute_hashes(img_bytes),
    )
    db.add(photo)
    db.flush()
    for project in refs:
        db.add(models.PhotoReference(photo_id=photo.id, project_name=project))
    db.commit()
    services.generate_candidates(db, photo)
    return photo


def main():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    if os.path.isdir(STORAGE_DIR):
        shutil.rmtree(STORAGE_DIR)
    os.makedirs(STORAGE_DIR)

    db = SessionLocal()
    try:
        sunset = draw_sunset()
        # 1. 原图（编辑授权，已被两个项目引用）
        save_photo(db, jpg_bytes(sunset, 92), "sunset_original.jpg", "张三", "editorial",
                   refs=["夏季旅游专题", "官网首页横幅"])
        # 2. 裁剪版（去掉边缘 12% 后重新保存）
        crop = sunset.crop((40, 25, W - 36, H - 26)).resize((W, H), Image.LANCZOS)
        save_photo(db, jpg_bytes(crop, 88), "sunset_crop_v2.jpg", "张三", "editorial")
        # 3. 高压缩 + 缩放再放大（反复上传导致）
        comp = sunset.resize((400, 263), Image.LANCZOS)
        comp = Image.open(BytesIO(jpg_bytes(comp, 30))).resize((W, H), Image.LANCZOS)
        save_photo(db, jpg_bytes(comp, 85), "sunset_compressed.jpg", "张三", "editorial",
                   refs=["公众号推文"])
        # 4. 同场景不同照片：太阳位置不同、云不同、多了飞鸟 → 误判样例
        alt = draw_sunset(sun_x=380, sun_y=150, clouds=((110, 95, 170), (320, 55, 180)), birds=((200, 90), (250, 70)))
        save_photo(db, jpg_bytes(alt, 92), "sunset_alt_shot.jpg", "张三", "editorial")
        # 5. 与原图几乎相同，但授权范围是 commercial → 演示授权不同禁止合并
        save_photo(db, jpg_bytes(sunset, 90), "sunset_agency_license.jpg", "图库代理", "commercial")

        studio = draw_studio()
        # 6-7. 静物原图 + 裁剪版
        save_photo(db, jpg_bytes(studio, 92), "studio_original.jpg", "李四", "internal",
                   refs=["产品手册 2026"])
        save_photo(db, jpg_bytes(studio.crop((30, 20, W - 30, H - 20)).resize((W, H)), 88),
                   "studio_crop.jpg", "李四", "internal")

        # 8-9. 互不相关的照片
        save_photo(db, jpg_bytes(draw_portrait(), 90), "portrait.jpg", "王五", "editorial")
        save_photo(db, jpg_bytes(draw_night(), 90), "night_city.jpg", "王五", "commercial")

        pending = db.query(models.SimilarityCandidate).filter_by(status="pending").count()
        print(f"已生成 {db.query(models.Photo).count()} 张照片，{pending} 条待审查相似候选")
    finally:
        db.close()


if __name__ == "__main__":
    main()
