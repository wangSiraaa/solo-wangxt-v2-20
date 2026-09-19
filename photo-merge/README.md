# 图库相似照片人工归并系统

面向图库编辑的"摄影师反复上传相似照片"整理工具：

- **Vue 3**：接触印样、相似候选人工审查、主图选择、归并、撤销与引用追踪页面；
- **FastAPI + Pillow**：上传管线（裁剪 / 长边限尺寸 / JPEG 压缩）、sha256 与 64bit pHash
  感知哈希（纯 Python DCT，无 numpy 依赖）；
- **PostgreSQL**（SQLAlchemy ORM；未配置时自动落到 SQLite 零依赖试跑）：
  原始文件索引、相似关系、引用项目、归并操作与撤销快照、审计流水；
- 图像原件与缩略图保存在**本地文件目录** `backend/storage/`。

## 核心业务规则（全部在后端强约束）

1. **哈希接近只产生候选**：pHash 汉明距离 ≤ `PHASH_THRESHOLD`（默认 16）或 sha256
   完全一致，只会生成 `pending` 候选，系统**绝不自动删除或归并任何照片**。
2. **不同授权范围禁止直接归并**：归并接口逐一校验 `license_scope`，不一致直接 `409`。
3. **归并不破坏可追踪性**：原文件保留在磁盘；副本 `primary_id` 指向主图；
   摄影师署名、原文件名、sha256/pHash、归并前的引用指向全部保留；引用可沿
   `primary_id` 链解析到当前取图。
4. **撤销恢复原有集合**：归并时保存完整快照（照片状态 + 受影响引用），撤销时还原；
   **归并之后才新增的引用不自动回退**，以 `needs_manual_review` 返回，
   由编辑在页面上逐条人工改指到具体原图。
5. **误判处理留档**：候选可驳回并要求填写理由（"同场景不同照片"的说明永久保留在
   候选记录与审计流水中）。

## 页面

| 路由 | 功能 |
|---|---|
| `/upload` | 拖拽/点选上传；图上拖框做归一化裁剪；填写署名、授权、说明；显示上传进度 |
| `/sheet` | 接触印样（全部/独立主图/已归并副本），多选 → 选主图 → 归并；授权不一致时即时红标提示 |
| `/candidates` | 待审查 / 已判误判 / 已据以归并 三栏；边缘距离红标；驳回必填理由；单对直接归并 |
| `/merges` | 归并组时间线（主图/副本条带）、撤销、撤销后对"新引用"的人工改指面板 |
| `/photos/:id` | 原文件索引详情：存储名、sha256、pHash、署名、授权、引用列表与引用解析链路 |

## 快速开始（SQLite，零外部依赖）

```bash
# 后端
cd backend
pip install -r requirements.txt          # 或 python3 -m pip
uvicorn app.main:app --port 8000          # 自动建库建表

# 另一个终端：生成演示数据（程序化绘制，共 14 张 + 3 个项目 + 引用）
python seed_demo.py
python demo_walkthrough.py                # 可选：预置误判驳回 / 归并 / 跨授权拒绝 / 撤销样例

# 前端
cd frontend
npm install
npm run dev                               # http://localhost:5173 （代理到 8000）
```

生产形态：`npm run build` 后，FastAPI 会自动同源托管 `frontend/dist`，
直接访问 <http://localhost:8000> 即可。

## 使用 PostgreSQL

复制 `backend/.env.example` 为 `.env` 并设置：

```
DATABASE_URL=postgresql+psycopg2://editor:editor@localhost:5432/photo_merge
```

或一键编排（含 Postgres + 后端，构建前端后启动）：

```bash
cd frontend && npm install && npm run build && cd ..
docker compose up --build
# 进入容器执行 seed:
docker compose exec backend python seed_demo.py
```

表结构（photos / projects / photo_refs / similarity_candidates / merge_records /
audit_logs）在应用启动时自动创建；`init.sql` 仅供已有实例手动建库参考。

## 演示数据里的样例（对应验收点）

| 文件 | 构造方式 | 预期 |
|---|---|---|
| `sunset_01` ~ `sunset_06` | 字节完全重复 / 重压缩(q42) / 调色 / 上传裁剪 / 缩放 | 距离 0~12，归并 |
| `sunset_07_other_photo` | 同一日落场景，前景由**帆船换成礁石群** | 距离 14，候选出现但应**判误判驳回**（理由留档） |
| `skyline_01` ~ `03` | 重压缩 / 轻微失焦 | 距离 0，归并 |
| `skyline_04_different_frame` | 同机位另一帧（多一栋楼入画） | 距离 6，**误判驳回** |
| `portrait_01` / `_02` | 同片输出，授权 editorial vs commercial | 有候选，但归并返回 409 |
| `forest_01` | 完全不同场景 | 无候选（对照） |

`demo_walkthrough.py` 还会在日落主图上制造一条"归并之后的新引用"；
到「归并 / 撤销」撤销日落组即可看到它被拦截并要求人工改指——
这就是"对归并之后的新引用提示人工处理"的完整过程。

## 主要 API

```
POST   /api/photos                      multipart：file + photographer + license_scope + caption + crop(JSON)
GET    /api/photos?status=all|active|merged
GET    /api/photos/{id}                 含引用列表
GET    /api/candidates?status=pending|rejected|confirmed|all
POST   /api/candidates/{id}/reject      {"reason": "..."}   # 误判留档
POST   /api/candidates/rescan
POST   /api/merges                      {photo_ids, primary_photo_id, note, candidate_id?}
GET    /api/merges
POST   /api/merges/{id}/undo            返回 restored_photo_ids + post_merge_refs(需人工处理)
GET/POST /api/projects, /api/refs
GET    /api/refs/{id}/resolve           跟随 primary_id 的取图链路
PATCH  /api/refs/{id}/reassign          撤销后人工改指 {photo_id}
GET    /api/audit                       操作流水
```

交互文档：启动后访问 `/docs`。

## 目录

```
photo-merge/
├── backend/
│   ├── app/
│   │   ├── main.py        # 路由 + 静态/SPA 托管
│   │   ├── services.py    # 候选生成 / 归并校验 / 撤销恢复 / 引用解析
│   │   ├── imaging.py     # Pillow 处理：裁剪/压缩/缩略图/pHash/汉明距离
│   │   ├── models.py      # 6 张表的 ORM
│   │   ├── schemas.py     # pydantic 模型
│   │   ├── config.py / database.py
│   ├── seed_demo.py       # 样例图像与数据生成
│   ├── demo_walkthrough.py# 完整工作流脚本
│   └── storage/           # originals/ + thumbs/ + SQLite（均为运行期生成）
├── frontend/src/          # Vue 3 页面（pages/）与 API 封装
└── docker-compose.yml
```
