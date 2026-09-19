import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 默认使用 PostgreSQL（见根目录 docker-compose.yml）。
# 本地无 PostgreSQL 时可设 DATABASE_URL=sqlite:///./gallery.db 临时运行。
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://gallery:gallery@localhost:5432/gallery",
)

# 本地文件目录存放图像
STORAGE_DIR = os.getenv("STORAGE_DIR", os.path.join(BASE_DIR, "storage"))

# 感知哈希相似阈值（汉明距离，64 位哈希）
PHASH_THRESHOLD = int(os.getenv("PHASH_THRESHOLD", "10"))
DHASH_THRESHOLD = int(os.getenv("DHASH_THRESHOLD", "8"))

# 允许的授权范围
LICENSE_SCOPES = ["editorial", "commercial", "internal"]
