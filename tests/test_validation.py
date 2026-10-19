"""
测试组 3/3：输入校验（缺字段、多字段、类型错、空对象、方法错）。
这一组是老师最看重的"边界情况"：
非法输入必须被拒，而且要能指出是哪个字段。
"""

import pytest


def test_missing_feature_is_reported(client, payload):
    payload["features"].pop("duration")
    response = client.post("/predict", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "duration"
    assert response.json()["detail"][0]["type"] == "value_error.missing"


def test_extra_feature_is_reported(client, payload):
    payload["features"]["not_a_feature"] = 1.0
    response = client.post("/predict", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "not_a_feature"


def test_empty_features_returns_422(client):
    assert client.post("/predict", json={"features": {}}).status_code == 422


@pytest.mark.parametrize(
    "bad_value",
    ["abc", None, [1, 2], {"nested": 1}],
    ids=["string", "null", "list", "object"],
)
def test_wrong_value_type_returns_422(client, payload, bad_value):
    payload["features"]["duration"] = bad_value
    assert client.post("/predict", json=payload).status_code == 422


def test_missing_body_returns_422(client):
    assert client.post("/predict").status_code == 422


def test_unknown_top_level_field_returns_422(client, payload):
    assert client.post("/predict", json={**payload, "not_allowed": 1}).status_code == 422


def test_wrong_http_method_returns_405(client):
    assert client.get("/predict").status_code == 405


def test_non_json_body_returns_422(client):
    response = client.post(
        "/predict",
        content=b"not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
