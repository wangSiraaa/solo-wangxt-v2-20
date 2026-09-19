"""运行期配置：所有值均可由环境变量覆盖。"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


DATABASE_URL = _env(
    "DATABASE_URL",
    f"sqlite:///{BASE_DIR / 'storage' / 'photo_merge.db'}",
)
STORAGE_DIR = Path(_env("STORAGE_DIR", str(BASE_DIR / "storage")))
ORIGINAL_DIR = STORAGE_DIR / "originals"
THUMB_DIR = STORAGE_DIR / "thumbs"

PHASH_THRESHOLD = int(_env("PHASH_THRESHOLD", "16"))
MAX_DIMENSION = int(_env("MAX_DIMENSION", "2000"))
JPEG_QUALITY = int(_env("JPEG_QUALITY", "85"))
THUMB_SIZE = int(_env("THUMB_SIZE", "320"))

# 授权范围的展示顺序，仅用于界面分组
LICENSE_SCOPES = ["internal", "editorial", "commercial", "exclusive"]

for _d in (STORAGE_DIR, ORIGINAL_DIR, THUMB_DIR):
    _d.mkdir(parents=True, exist_ok=True)
