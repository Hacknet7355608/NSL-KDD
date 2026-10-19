"""配置层测试（对应课件 5.1-12 Factor Config 第 15 页：用 monkeypatch 测配置）。

覆盖三件事：
  1. 配置确实从环境变量读（而不是写死在代码里）
  2. 未设置时回落到安全的默认值
  3. 敏感值不会通过 safe_view 泄漏
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings, get_settings, validate_for_env


def test_reads_values_from_environment(monkeypatch):
    """设置环境变量后，Settings 必须读到它们（证明配置外置生效）。"""
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("MODEL_PATH", "/srv/models/m.joblib")

    settings = get_settings()

    assert settings.app_env == "staging"
    assert settings.log_level == "DEBUG"
    assert settings.model_path == "/srv/models/m.joblib"


def test_defaults_when_not_set(monkeypatch):
    """什么都不设时，非敏感配置回落到默认值，且启动不报错。"""
    for name in ("APP_ENV", "LOG_LEVEL", "MODEL_PATH", "MODEL_META_PATH", "APP_API_KEY"):
        monkeypatch.delenv(name, raising=False)

    settings = get_settings()

    assert settings.app_env == "dev"
    assert settings.log_level == "INFO"
    assert settings.model_path == "models/model.joblib"
    assert settings.api_key_configured is False


def test_safe_view_never_exposes_secret(monkeypatch):
    """safe_view 只能表达"有没有配"，绝不能出现密钥原文。"""
    monkeypatch.setenv("APP_API_KEY", "super-secret-key")
    monkeypatch.setenv("APP_ENV", "production")

    view = get_settings().safe_view()

    assert view["api_key_configured"] is True
    assert "super-secret-key" not in str(view)


def test_production_requires_api_key():
    """fail fast：生产环境缺密钥时直接退出，不允许带病上线。"""
    settings = Settings(APP_ENV="production", APP_API_KEY=None)

    with pytest.raises(SystemExit):
        validate_for_env(settings)


def test_production_with_key_passes():
    """生产环境提供了密钥则校验通过。"""
    settings = Settings(APP_ENV="production", APP_API_KEY="k")

    validate_for_env(settings)  # 不抛异常即通过


def test_config_endpoint_reflects_env_without_leaking(monkeypatch, tmp_path):
    """GET /config 展示当前环境，但绝不返回密钥原文（12-Factor 的可视化证据）。"""
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("APP_API_KEY", "top-secret-value")

    client = TestClient(create_app(tmp_path / "m.joblib", tmp_path / "meta.json"))
    body = client.get("/config").json()

    assert body["app_env"] == "staging"
    assert body["api_key_configured"] is True
    assert "top-secret-value" not in str(body)


def test_health_response_keeps_its_contract(client):
    """/health 的返回体必须仍是 {"status", "model_loaded"} 两个键（接口契约）。"""
    body = client.get("/health").json()

    assert set(body) == {"status", "model_loaded"}
