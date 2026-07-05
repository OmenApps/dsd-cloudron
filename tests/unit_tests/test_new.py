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
    # The scaffolder always builds a greenfield config, which flips the readme's
    # SSO section to the "allauth wired" claim; drop this and every scaffolded
    # --sso readme would wrongly say allauth is not auto-wired.
    assert config.greenfield is True


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


def test_toggle_summary_lists_resolved_on_toggles():
    args = new.parse_args(["new", "My Shop", "--celery", "--sso"])
    summary = new.format_toggle_summary(new.build_context(args))
    assert "Redis: on" in summary
    assert "Sendmail: on" in summary
    assert "Celery: on" in summary
    assert "SSO: on" in summary


def test_toggle_summary_reflects_off_toggles():
    args = new.parse_args(["new", "My Shop", "--no-redis", "--no-sendmail"])
    summary = new.format_toggle_summary(new.build_context(args))
    assert "Redis: off" in summary
    assert "Sendmail: off" in summary
    assert "Celery: off" in summary
    assert "SSO: off" in summary


def test_main_prints_toggle_summary(monkeypatch, capsys):
    monkeypatch.setattr(new, "scaffold", lambda args: "/tmp/my_shop")
    new.main(["new", "My Shop", "--sso"])
    out = capsys.readouterr().out
    assert "SSO: on" in out
    assert "Celery: off" in out


def test_parse_reconfigure_command():
    args = new.parse_args(["reconfigure", "--memory-limit", "2147483648"])
    assert args.command == "reconfigure"
    assert args.memory_limit == 2147483648
    assert args.project_dir == "."


def test_reconfigure_subcommand_has_no_stack_flags():
    # Reconfigure re-renders the current config and adjusts sizing only; it never
    # toggles a stack, so the stack flags must not exist on this subparser.
    with pytest.raises(SystemExit):
        new.parse_args(["reconfigure", "--celery"])


def test_read_project_state_reconstructs_from_project(tmp_path):
    from dsd_cloudron.packaging import CloudronAppConfig, render_all

    render_all(
        CloudronAppConfig(
            project_name="shop",
            app_id="com.example.shop",
            pkg_manager="uv",
            enable_sso=True,
            greenfield=True,
        ),
        tmp_path,
    )
    state = new._read_project_state(tmp_path)
    assert state["project_name"] == "shop"
    assert state["app_id"] == "com.example.shop"
    assert state["pkg_manager"] == "uv"  # reconstructed from the Dockerfile
    assert state["greenfield"] is True  # greenfield SSO ships no cloudron_adapters.py
    assert state["enable_sso"] is True  # oidc addon present in the manifest
    assert state["enable_redis"] is True
    assert state["enable_celery"] is False  # no supervisor/celery-worker.conf


def test_read_project_state_marks_a_retrofit_sso_project_not_greenfield(tmp_path):
    from dsd_cloudron.packaging import CloudronAppConfig, render_all

    # A retrofit SSO deploy ships cloudron_adapters.py; reconstruction must read that
    # as greenfield=False so a re-render keeps the retrofit adapter pointers and the
    # req_txt Dockerfile instead of flipping to greenfield/uv.
    render_all(
        CloudronAppConfig(
            project_name="shop", app_id="com.example.shop", enable_sso=True
        ),
        tmp_path,
    )
    state = new._read_project_state(tmp_path)
    assert state["greenfield"] is False
    assert state["pkg_manager"] == "req_txt"
    assert (tmp_path / "shop" / "cloudron_adapters.py").exists()


def test_reconfigure_config_applies_sizing_overrides(tmp_path):
    from dsd_cloudron.packaging import CloudronAppConfig, render_all

    render_all(
        CloudronAppConfig(
            project_name="shop",
            app_id="com.example.shop",
            pkg_manager="uv",
            greenfield=True,
        ),
        tmp_path,
    )
    args = new.parse_args(
        [
            "reconfigure",
            "--project-dir",
            str(tmp_path),
            "--memory-limit",
            "2147483648",
        ]
    )
    config = new.reconfigure_config(tmp_path, args)
    assert config.memory_limit == 2147483648
    assert config.enable_redis is True  # kept from the project
    assert config.enable_celery is False  # kept from the project


def test_reconfigure_config_missing_manifest_fails_cleanly(tmp_path):
    args = new.parse_args(["reconfigure", "--project-dir", str(tmp_path)])
    with pytest.raises(SystemExit):
        new.reconfigure_config(tmp_path, args)


def test_run_reconfigure_overwrites_changed_file_on_yes(tmp_path, monkeypatch):
    from dsd_cloudron.packaging import CloudronAppConfig, render_all

    render_all(
        CloudronAppConfig(
            project_name="shop",
            app_id="com.example.shop",
            pkg_manager="uv",
            greenfield=True,
        ),
        tmp_path,
    )
    (tmp_path / "Dockerfile").write_text("HAND EDIT\n", encoding="utf-8")
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    args = new.parse_args(["reconfigure", "--project-dir", str(tmp_path)])
    new.run_reconfigure(args)
    assert "HAND EDIT" not in (tmp_path / "Dockerfile").read_text(encoding="utf-8")
