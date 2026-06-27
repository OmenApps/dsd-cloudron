import pytest

from dsd_cloudron.packaging import CloudronAppConfig


def test_config_defaults():
    config = CloudronAppConfig(project_name="blog", app_id="com.example.blog")
    assert config.project_name == "blog"
    assert config.app_id == "com.example.blog"
    assert config.pkg_manager == "req_txt"
    assert config.enable_redis is True
    assert config.enable_celery is False
    assert config.enable_sendmail is True
    assert config.enable_sso is False
    assert config.memory_limit == 1073741824
    assert config.http_port == 8000
    assert config.health_check_path == "/"


def test_config_toggles_off():
    # Celery stays off here: celery-without-redis is rejected (see next test).
    config = CloudronAppConfig(
        project_name="shop",
        app_id="com.example.shop",
        enable_redis=False,
        enable_sendmail=False,
        enable_celery=False,
        enable_sso=True,
    )
    assert config.enable_redis is False
    assert config.enable_celery is False
    assert config.enable_sso is True


def test_config_celery_requires_redis():
    with pytest.raises(ValueError):
        CloudronAppConfig(
            project_name="shop",
            app_id="com.example.shop",
            enable_celery=True,
            enable_redis=False,
        )
