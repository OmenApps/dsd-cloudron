import pytest
from cookiecutter.exceptions import OutputDirExistsException

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


def test_python_keyword_name_is_rejected():
    # "Class"/"For"/"Import" slugify to valid-looking identifiers that are reserved
    # words; `import class` is a SyntaxError, so the generated project would not
    # import. isidentifier() accepts them, so build_context must reject explicitly.
    for name in ("Class", "For", "import"):
        args = new.parse_args(["new", name])
        with pytest.raises(SystemExit):
            new.build_context(args)


def test_unsafe_characters_in_name_are_rejected():
    # The raw name is spliced verbatim into generated source (cookiecutter does not
    # autoescape), so quotes, backslashes, and angle brackets must be rejected
    # before they can break or inject into the rendered home view.
    for name in ('Joe "Big" Shop', "back\\slash", "<script>", "tab\tname"):
        args = new.parse_args(["new", name])
        with pytest.raises(SystemExit):
            new.build_context(args)


def test_all_punctuation_name_is_rejected():
    # Collapses to an empty slug, which is not a valid identifier.
    args = new.parse_args(["new", "!!!"])
    with pytest.raises(SystemExit):
        new.build_context(args)


def test_leading_or_trailing_underscore_name_is_rejected():
    # "_foo"/"foo_" are valid identifiers but hyphenate to an invalid reverse-DNS
    # app_id (leading/trailing hyphen), rejected only at `cloudron install`.
    for name in ("_foo", "foo_"):
        args = new.parse_args(["new", name])
        with pytest.raises(SystemExit):
            new.build_context(args)


def test_no_redis_and_no_sendmail_flags_disable_infra_toggles():
    # The default-ON toggles flip off via their --no-<x> form; assert the success
    # case directly (the guard test only exercises --no-redis through rejection).
    args = new.parse_args(["new", "My Shop", "--no-redis", "--no-sendmail"])
    context = new.build_context(args)
    assert context["use_redis"] == "no"
    assert context["use_sendmail"] == "no"


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


def test_config_from_context_maps_false_toggles():
    # The all-"yes" case above would still pass if the "== 'yes'" check were
    # inverted; assert the False direction so a polarity flip is caught.
    context = {
        "project_slug": "my_shop",
        "app_id": "com.example.my-shop",
        "use_redis": "no",
        "use_sendmail": "no",
        "use_celery": "no",
        "use_sso": "no",
    }
    config = new.config_from_context(context)
    assert config.enable_redis is False
    assert config.enable_sendmail is False
    assert config.enable_celery is False
    assert config.enable_sso is False


def test_main_returns_zero_and_prints_path(monkeypatch, capsys):
    # main() wires scaffold + reports the path; stub scaffold so no cookiecutter
    # template or filesystem is needed (scaffold's full path is covered by bakes).
    monkeypatch.setattr(new, "scaffold", lambda args: "/tmp/my_shop")
    result = new.main(["new", "My Shop"])
    assert result == 0
    assert "/tmp/my_shop" in capsys.readouterr().out


def test_scaffold_existing_output_dir_fails_cleanly(monkeypatch):
    # cookiecutter raises OutputDirExistsException on a re-run; scaffold must turn
    # that into a clean SystemExit rather than a raw traceback.
    def _raise(*args, **kwargs):
        raise OutputDirExistsException('"/tmp/my_shop" already exists')

    monkeypatch.setattr(new, "cookiecutter", _raise)
    args = new.parse_args(["new", "My Shop", "--output-dir", "/tmp"])
    with pytest.raises(SystemExit):
        new.scaffold(args)
