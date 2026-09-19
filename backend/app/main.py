import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from .routers import candidates, merges, photos

Base.metadata.create_all(engine)

app = FastAPI(title="图库相似照片归并系统", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(photos.router)
app.include_router(candidates.router)
app.include_router(merges.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# 生产模式：若前端已构建，直接由 FastAPI 托管（history 路由回退到 index.html）。
# 注意：mount("/") 必须最后注册，否则会吞掉后定义的 /api 路由。
class SPAStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        from starlette.exceptions import HTTPException as StarletteHTTPException

        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "frontend", "dist")
if os.path.isdir(dist):
    app.mount("/", SPAStaticFiles(directory=dist, html=True), name="frontend")
