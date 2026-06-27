import argparse

import pytest

from dsd_cloudron import cli
from dsd_cloudron.plugin_config import plugin_config
from django_simple_deploy.management.commands.utils.plugin_utils import dsd_config
from django_simple_deploy.management.commands.utils.command_errors import (
    DSDCommandError,
)


def _options(**overrides):
    base = {
        "location": "blog",
        "app_id": "",
        "memory_limit": 1073741824,
        "health_check_path": "/",
        "force_overwrite": False,
        "server": "",
        "allow_selfsigned": False,
        "no_redis": False,
        "no_sendmail": False,
        "celery": False,
        "sso": False,
    }
    base.update(overrides)
    return base


def test_validate_cli_writes_defaults_onto_config():
    cli.validate_cli(_options())
    assert plugin_config.location == "blog"
    assert plugin_config.enable_redis is True
    assert plugin_config.enable_sendmail is True
    assert plugin_config.enable_celery is False
    assert plugin_config.enable_sso is False


def test_validate_cli_maps_all_passthrough_fields():
    # Pass distinctive non-default values so a mis-keyed mapping (e.g. reading
    # options["app-id"]) would surface here.
    cli.validate_cli(
        _options(
            location="news",
            app_id="io.omenapps.news",
            memory_limit=2147483648,
            health_check_path="/healthz/",
            force_overwrite=True,
            server="my.example.com",
            allow_selfsigned=True,
        )
    )
    assert plugin_config.location == "news"
    assert plugin_config.app_id == "io.omenapps.news"
    assert plugin_config.memory_limit == 2147483648
    assert plugin_config.health_check_path == "/healthz/"
    assert plugin_config.force_overwrite is True
    assert plugin_config.server == "my.example.com"
    assert plugin_config.allow_selfsigned is True


def test_validate_cli_inverts_opt_out_flags():
    cli.validate_cli(_options(no_redis=True, no_sendmail=True))
    assert plugin_config.enable_redis is False
    assert plugin_config.enable_sendmail is False


def test_validate_cli_sets_app_intrusive_flags():
    cli.validate_cli(_options(celery=True, sso=True))
    assert plugin_config.enable_celery is True
    assert plugin_config.enable_sso is True


def test_validate_cli_rejects_celery_without_redis():
    with pytest.raises(DSDCommandError):
        cli.validate_cli(_options(celery=True, no_redis=True))


def test_validate_cli_rejects_missing_location_with_automate_all():
    dsd_config.automate_all = True
    with pytest.raises(DSDCommandError):
        cli.validate_cli(_options(location=""))


def test_validate_cli_accepts_location_with_automate_all():
    dsd_config.automate_all = True
    cli.validate_cli(_options(location="blog"))  # must not raise
    assert plugin_config.location == "blog"


@pytest.mark.parametrize(
    "field, value",
    [
        ("location", "my blog"),
        ("location", 'bad"name'),
        ("location", "a;rm -rf"),
        ("server", "my host.com"),
        ("server", "host`whoami`"),
    ],
)
def test_validate_cli_rejects_unsafe_location_and_server(field, value):
    with pytest.raises(DSDCommandError):
        cli.validate_cli(_options(**{field: value}))


def test_validate_cli_accepts_normal_location_and_server():
    cli.validate_cli(_options(location="my-blog", server="my.example.com"))
    assert plugin_config.location == "my-blog"
    assert plugin_config.server == "my.example.com"


def test_parser_registration_adds_flags():
    parser = argparse.ArgumentParser()
    cli.PluginCLI(parser)
    text = parser.format_help()
    for flag in ["--location", "--no-redis", "--celery", "--sso", "--force-overwrite"]:
        assert flag in text
    # The API token is intentionally not a CLI flag (it would be logged to
    # dsd_logs and shell history); auth comes from the `cloudron login` session.
    assert "--token" not in text
