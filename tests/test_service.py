"""
测试组 1/3：服务能启动、元信息端点可用。
对应老师要求："至少 3 个有意义的测试，每个包含多个边界情况"。
本文件覆盖的是「服务可用性」这一个功能点。
"""

import pytest


def test_root_reports_service(client):
    body = client.get("/").json()
    assert body["service"] == "nsl-kdd"


def test_health_reports_model_loaded(client):
    assert client.get("/health").json() == {"status": "ok", "model_loaded": True}


def test_model_info_exposes_contract(client):
    body = client.get("/model-info").json()
    assert body["n_features"] == 6
    assert body["classes"] == ["DoS", "Probe", "R2L", "U2R", "normal"]
    assert body["mlflow_run_id"] == "test-run-id"
    assert body["data_version"] == "0" * 32


def test_sample_contains_every_feature(client):
    body = client.get("/sample").json()
    assert len(body["features"]) == 6
    assert set(body["features"].values()) == {0.0}


@pytest.mark.parametrize("path", ["/unknown", "/predicts"])
def test_unknown_route_returns_404(client, path):
    assert client.get(path).status_code == 404
