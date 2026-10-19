"""
额外一组：模型缺失/损坏时的降级行为。
服务要能起来（/health 200），但预测接口明确返回 503 并说明原因。
这是"模型是外部产物"的项目里最容易被忽略的边界：CI 与镜像初次构建时没有模型。
"""

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_is_ok_without_model(tmp_path):
    with TestClient(create_app(tmp_path / "nope.joblib", tmp_path / "nope.json")) as client:
        assert client.get("/health").json() == {"status": "ok", "model_loaded": False}


def test_predict_returns_503_without_model(tmp_path, payload):
    with TestClient(create_app(tmp_path / "nope.joblib", tmp_path / "nope.json")) as client:
        response = client.post("/predict", json=payload)
    assert response.status_code == 503
    assert "模型" in response.json()["detail"]


def test_model_info_returns_503_without_model(tmp_path):
    with TestClient(create_app(tmp_path / "nope.joblib", tmp_path / "nope.json")) as client:
        assert client.get("/model-info").status_code == 503


def test_broken_meta_returns_503(tmp_path, model_dir, payload):
    broken = tmp_path / "model_meta.json"
    broken.write_text("{oops", encoding="utf-8")
    with TestClient(create_app(model_dir / "model.joblib", broken)) as client:
        assert client.post("/predict", json=payload).status_code == 503
