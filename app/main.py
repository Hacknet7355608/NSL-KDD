"""FastAPI 入口（占位实现）。

真实业务代码到位后，用正式实现整体覆盖本文件即可，但请保留两个约定：

1. 模块内存在名为 ``app`` 的 ASGI 对象 —— Dockerfile 的
   ``uvicorn app.main:app`` 依赖它；
2. ``GET /health`` 返回 HTTP 200 —— Dockerfile 的 HEALTHCHECK 与
   CI 的容器冒烟脚本都打这个探针。
"""

from fastapi import FastAPI

app = FastAPI(title="NSL-KDD", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """存活探针，供 Docker HEALTHCHECK 与 CI 冒烟测试使用。"""
    return {"status": "ok"}
