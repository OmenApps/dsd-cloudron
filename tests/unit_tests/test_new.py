import pytest

from dsd_cloudron import new
from dsd_cloudron.packaging import CloudronAppConfig


def test_parse_new_command():
    args = new.parse_args(["new", "My Shop"])
    assert args.command == "new"
    assert args.project_name == "My Shop"


def test_build_context_slugifies_and_carries_toggles():
    args = new.parse_args(["new", "My Shop", "--celery", "--sso"])
    context = new.build_context(args)
    assert context["project_name"] == "My Shop"
    assert context["project_slug"] == "my_shop"
    # app_id is reverse-DNS, so underscores become hyphens (see _slugify / build_context).
    assert context["app_id"] == "com.example.my-shop"
    assert context["use_celery"] == "yes"
    assert context["use_sso"] == "yes"
    # Defaults: redis + sendmail on (infra), ninja/htmx/s3 off (lean).
    assert context["use_redis"] == "yes"
    assert context["use_sendmail"] == "yes"
    assert context["use_ninja"] == "no"


def test_celery_without_redis_is_rejected_before_cookiecutter():
    # M0's CloudronAppConfig forbids enable_celery without enable_redis; greenfield
    # must reject the combo up front (with a clean message) rather than write a
    # half-baked project to disk and then blow up in config_from_context.
    args = new.parse_args(["new", "My Shop", "--celery", "--no-redis"])
    with pytest.raises(SystemExit):
        new.build_context(args)


def test_bad_project_name_is_rejected_before_cookiecutter():
    # A name that does not slugify to a valid Python identifier (leading digit,
    # empty, all-punctuation) would later raise a raw ValueError in
    # CloudronAppConfig.__post_init__ after cookiecutter already wrote the tree.
    args = new.parse_args(["new", "123"])
    with pytest.raises(SystemExit):
        new.build_context(args)


def test_config_from_context_maps_to_cloudron_app_config():
    context = {
        "project_slug": "my_shop",
        "app_id": "com.example.my-shop",
        "use_redis": "yes",
        "use_sendmail": "yes",
        "use_celery": "yes",
        "use_sso": "yes",
    }
    config = new.config_from_context(context)
    assert isinstance(config, CloudronAppConfig)
    assert config.project_name == "my_shop"
    assert config.app_id == "com.example.my-shop"
    assert config.pkg_manager == "uv"
    assert config.health_check_path == "/healthz/"
    assert config.enable_redis is True
    assert config.enable_sendmail is True
    assert config.enable_celery is True
    assert config.enable_sso is True
