"""冒烟测试：在真实测试用例到位前保证流水线仍有意义。

覆盖两条对部署有约束的契约：``app.main:app`` 可导入、``/health`` 返回 200。
正式测试写好后可以整文件删除或替换。
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_unknown_path_returns_404() -> None:
    assert client.get("/__nope__").status_code == 404
