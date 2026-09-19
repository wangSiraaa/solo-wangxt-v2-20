# 图库相似照片归并系统

图库编辑整理摄影师反复上传的相似照片的人工确认归并系统。

- **Vue 3**：接触印样、相似候选审查、主图选择、归并与撤销页面
- **FastAPI + Pillow**：上传接口、感知哈希（aHash/dHash/pHash）计算
- **PostgreSQL**：原始文件索引、相似关系、归并操作（本地无 PG 时可用 SQLite 兜底运行）
- **本地文件目录**：图像文件存于 `backend/storage/`

## 核心规则

1. **哈希接近只产生候选**：上传后与库中 active 照片比对，距离小于阈值仅生成
   `SimilarityCandidate`（pending），绝不自动删除图片。
2. **归并必经人工**：候选需人工「确认相似」后才能归并；每张非主图都必须与主图存在
   已确认的候选，否则接口返回 409。
3. **授权范围不同不允许直接合并**：`license_scope` 不一致的照片归并时返回 409 及明细。
4. **可追踪**：归并只把非主图状态置为 `merged`，原文件、摄影师署名、项目引用全部保留。
5. **可撤销**：撤销归并恢复原有集合；归并之后新增的引用会被标记 `needs_manual_review`，
   在界面上提示人工处理。
6. **误判处理**：人工判定「不相似」的候选置为 `rejected`，两张照片完整保留，
   候选关闭不再出现，误判记录留痕可查。

## 快速开始

### 方式一：Docker Compose（PostgreSQL）

```bash
docker compose up --build
# 后端 http://localhost:8000 （首次启动自动建表并生成演示数据）
```

### 方式二：本地开发

```bash
# 后端（无 PostgreSQL 时可用 SQLite 临时运行）
cd backend
pip install -r requirements.txt
export DATABASE_URL="sqlite:///./gallery.db"   # 生产用 postgresql+psycopg2://gallery:gallery@localhost:5432/gallery
python -m app.seed                             # 生成演示图片与候选
uvicorn app.main:app --port 8000

# 前端（另开终端）
cd frontend
npm install
npm run dev        # http://localhost:5173 ，/api 代理到 8000
# 或 npm run build 后由 FastAPI 直接托管 dist（http://localhost:8000）
```

## 演示数据与误判样例

`python -m app.seed` 用 Pillow 程序化生成 9 张照片：

| 照片 | 说明 |
|---|---|
| sunset_original / sunset_crop_v2 / sunset_compressed | 原图 / 裁剪版 / 高压缩缩放版 → 真重复 |
| sunset_alt_shot | **同场景不同照片**（太阳位置、云、飞鸟不同），dHash 距离落入阈值被标为候选 → **误判样例**，应人工驳回 |
| sunset_agency_license | 与原图几乎相同但授权为 commercial → 演示「不同授权不允许合并」 |
| studio_original / studio_crop | 静物原图 + 裁剪版 |
| portrait / night_city | 互不相关，不产生候选 |

## 演示流程

1. **上传页**：查看接触印样（缩略图网格、署名、授权、引用），可上传新图触发候选生成。
2. **候选审查页**：
   - 待审查列表并排对比两张照片（含 pHash/dHash 距离）；
   - 对 sunset_alt_shot 的候选点「误判（不相似）」→ 进入误判记录，照片保留；
   - 对真重复点「确认相似」→ 进入相似组，点击照片选主图后归并；
   - 含 sunset_agency_license 的组会显示「授权范围不一致，不可合并」。
3. **归并记录页**：查看归并组成员（主图标识）、各照片的引用项目；
   可给成员「新增引用」后「撤销归并」→ 集合恢复，归并期间新增的引用被标记
   「需人工处理」并弹出提示。

## API 摘要

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/photos/upload` | 上传（multipart：file/photographer/license_scope/project_name） |
| GET | `/api/photos` · `/api/photos/{id}` · `/api/photos/{id}/file` | 列表 / 详情 / 图像文件 |
| POST | `/api/photos/{id}/references` | 新增项目引用 |
| GET | `/api/candidates?status=pending` | 候选列表 |
| POST | `/api/candidates/{id}/confirm` · `/reject` | 确认相似 / 误判驳回 |
| POST | `/api/merges` | 归并（校验授权一致 + 候选已人工确认） |
| GET | `/api/merges` | 归并记录 |
| POST | `/api/merges/{id}/undo` | 撤销归并，返回需人工处理的引用 |

## 目录结构

```
backend/app/
  main.py        FastAPI 入口，托管前端 dist
  config.py      DATABASE_URL / STORAGE_DIR / 哈希阈值
  models.py      Photo / PhotoReference / SimilarityCandidate / MergeGroup / MergeMember
  hashing.py     aHash/dHash/pHash（Pillow + numpy，DCT 自实现）
  services.py    候选生成、归并校验、撤销与引用标记
  seed.py        演示图片生成（裁剪/压缩/同场景不同照片）
  routers/       photos / candidates / merges
frontend/src/
  views/UploadView.vue   上传 + 接触印样
  views/ReviewView.vue   候选审查、误判处理、选主图归并
  views/MergesView.vue   归并记录、新增引用、撤销
```
