import pytest

from dsd_cloudron.packaging import CloudronAppConfig, _context


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
    assert config.version == "1.0.0"


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
    assert config.enable_sendmail is False
    assert config.enable_sso is True


def test_config_celery_requires_redis():
    with pytest.raises(ValueError):
        CloudronAppConfig(
            project_name="shop",
            app_id="com.example.shop",
            enable_celery=True,
            enable_redis=False,
        )


def test_config_celery_with_redis_succeeds():
    # The valid Celery configuration must construct without error; this guards
    # the non-raising branch of the __post_init__ guard.
    config = CloudronAppConfig(
        project_name="shop",
        app_id="com.example.shop",
        enable_celery=True,
        enable_redis=True,
    )
    assert config.enable_celery is True
    assert config.enable_redis is True


def test_config_rejects_invalid_project_name():
    # project_name is spliced into generated Python and templates, so a name
    # that is not a valid identifier (quote, space, dot, dash) must be rejected.
    for bad in ('blog"; import os', "my blog", "com.example.blog", "my-blog"):
        with pytest.raises(ValueError):
            CloudronAppConfig(project_name=bad, app_id="com.example.blog")


def test_config_rejects_unknown_pkg_manager():
    with pytest.raises(ValueError):
        CloudronAppConfig(
            project_name="blog", app_id="com.example.blog", pkg_manager="conda"
        )


def test_config_accepts_all_supported_pkg_managers():
    for manager in ("req_txt", "poetry", "pipenv", "uv"):
        config = CloudronAppConfig(
            project_name="blog", app_id="com.example.blog", pkg_manager=manager
        )
        assert config.pkg_manager == manager


def test_display_title_derived_from_project_name():
    config = CloudronAppConfig(project_name="my_blog", app_id="com.example.my_blog")
    assert config.display_title() == "My Blog"


def test_display_title_explicit_overrides_derivation():
    config = CloudronAppConfig(
        project_name="my_blog",
        app_id="com.example.my_blog",
        title="My Custom Blog",
    )
    assert config.display_title() == "My Custom Blog"


def test_context_values_are_render_safe():
    # The standalone Engine localizes non-string ints/floats through global
    # settings during rendering, which raises offline. Every context value must
    # therefore be a str or a bool (bool is localization-safe).
    config = CloudronAppConfig(project_name="blog", app_id="com.example.blog")
    for key, value in _context(config).items():
        assert isinstance(value, (str, bool)), f"{key} is {type(value).__name__}"
