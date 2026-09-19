# 数据库无需手工建表：应用启动时 SQLAlchemy 自动 create_all。
# 此文件仅记录建库参数，供已有 PostgreSQL 实例手动初始化时参考。
CREATE DATABASE photo_merge;
CREATE USER editor WITH PASSWORD 'editor';
GRANT ALL PRIVILEGES ON DATABASE photo_merge TO editor;
