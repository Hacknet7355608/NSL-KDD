"""
测试组 2/3：预测接口的契约与数值边界。
覆盖：全 0、1.0、负数、1e6、小数、幂等性、/sample 返回的 payload 能直接提交。
"""

import math

import pytest


@pytest.mark.parametrize(
    "value",
    [0.0, 1.0, -1.0, 1e6, 12.5],
    ids=["zero", "one", "negative", "huge", "float"],
)
def test_predict_accepts_boundary_values(client, payload, value):
    payload["features"] = {name: value for name in payload["features"]}
    response = client.post("/predict", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["prediction"] in body["probabilities"]
    assert 0.0 <= body["confidence"] <= 1.0
    assert math.isclose(sum(body["probabilities"].values()), 1.0, abs_tol=0.02)


def test_confidence_is_the_max_probability(client, payload):
    body = client.post("/predict", json=payload).json()
    assert body["confidence"] == max(body["probabilities"].values())


def test_predict_is_deterministic(client, payload):
    first = client.post("/predict", json=payload).json()
    second = client.post("/predict", json=payload).json()
    assert first == second


def test_sample_can_be_posted_back(client):
    sample = client.get("/sample").json()
    assert client.post("/predict", json=sample).status_code == 200
