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


def test_edge_dash_name_slugs_to_edge_underscore_and_is_rejected():
    # A trailing dash passes the raw-character check (dashes are allowed) but _slugify
    # turns it into a trailing underscore, which hyphenates back to an invalid app_id
    # label. This is the input that actually reaches the app_id underscore guard - a
    # raw "foo_" is stopped earlier by the character check, which forbids underscores.
    args = new.parse_args(["new", "foo-"])  # -> slug "foo_"
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


def test_main_dispatches_the_reconfigure_subcommand(monkeypatch):
    # The reconfigure subcommand must route through run_reconfigure and return 0; stub
    # run_reconfigure (its own path is covered above) to test main's dispatch in isolation.
    calls = []
    monkeypatch.setattr(new, "run_reconfigure", lambda args: calls.append(args))
    result = new.main(["reconfigure", "--project-dir", "/tmp/whatever"])
    assert result == 0
    assert len(calls) == 1
    assert calls[0].command == "reconfigure"


def test_scaffold_existing_output_dir_fails_cleanly(monkeypatch):
    # cookiecutter raises OutputDirExistsException on a re-run; scaffold must turn
    # that into a clean SystemExit rather than a raw traceback.
    def _raise(*args, **kwargs):
        raise OutputDirExistsException('"/tmp/my_shop" already exists')

    monkeypatch.setattr(new, "cookiecutter", _raise)
    args = new.parse_args(["new", "My Shop", "--output-dir", "/tmp"])
    with pytest.raises(SystemExit):
        new.scaffold(args)


def test_scaffold_render_failure_fails_cleanly_and_names_the_dir(monkeypatch):
    # cookiecutter wrote the skeleton, but the deploy artifacts then fail to render, so
    # the tree is half-built. scaffold must abort cleanly and name the directory to
    # remove rather than leave a raw traceback that also blocks a same-name retry.
    monkeypatch.setattr(new, "cookiecutter", lambda *a, **k: "/tmp/my_shop")

    def _boom(*a, **k):
        raise RuntimeError("template kaboom")

    monkeypatch.setattr(new, "render_all", _boom)
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


def test_reconfigure_config_applies_health_check_override(tmp_path):
    from dsd_cloudron.packaging import CloudronAppConfig, render_all

    # --health-check-path is one of the two reconfigure scalar overrides; it must reach
    # the reconstructed config. The rendered project keeps the default "/", so overriding
    # to a distinct path proves the override arm ran (not the reconstructed value).
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
            "--health-check-path",
            "/status/",
        ]
    )
    config = new.reconfigure_config(tmp_path, args)
    assert config.health_check_path == "/status/"


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


def test_run_reconfigure_aborts_cleanly_if_render_raises_reconfigure_error(
    tmp_path, monkeypatch
):
    from dsd_cloudron.packaging import (
        CloudronAppConfig,
        ReconfigureError,
        render_all,
    )

    # reconfigure_config already validated the on-disk state, so this catch only fires if
    # the manifest changes underfoot between the two reads. Simulate that race and confirm
    # run_reconfigure aborts cleanly (SystemExit) rather than surfacing a raw traceback.
    render_all(
        CloudronAppConfig(
            project_name="shop",
            app_id="com.example.shop",
            pkg_manager="uv",
            greenfield=True,
        ),
        tmp_path,
    )

    def _raise(*a, **k):
        raise ReconfigureError("manifest changed underfoot")

    monkeypatch.setattr(new, "reconfigure", _raise)
    args = new.parse_args(["reconfigure", "--project-dir", str(tmp_path)])
    with pytest.raises(SystemExit):
        new.run_reconfigure(args)


def test_run_reconfigure_leaves_file_on_no(tmp_path, monkeypatch, capsys):
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
    # Declining leaves the file exactly as edited and reports no changes; this proves
    # new.py's own _confirm closure and the "no changes" branch, not just packaging.
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    args = new.parse_args(["reconfigure", "--project-dir", str(tmp_path)])
    new.run_reconfigure(args)
    assert (tmp_path / "Dockerfile").read_text(encoding="utf-8") == "HAND EDIT\n"
    assert "No changes were made" in capsys.readouterr().out


def test_run_reconfigure_applies_memory_limit_to_manifest(tmp_path, monkeypatch):
    import json

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
    # End-to-end: the --memory-limit CLI arg must reach the written manifest. Only the
    # manifest scalar changes, so nothing is diffed or prompted (input is a safety net).
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    args = new.parse_args(
        ["reconfigure", "--project-dir", str(tmp_path), "--memory-limit", "2147483648"]
    )
    new.run_reconfigure(args)
    manifest = json.loads(
        (tmp_path / "CloudronManifest.json").read_text(encoding="utf-8")
    )
    assert manifest["memoryLimit"] == 2147483648


def test_run_reconfigure_aborts_cleanly_without_a_tty(tmp_path, monkeypatch):
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

    def _no_stdin(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", _no_stdin)
    args = new.parse_args(["reconfigure", "--project-dir", str(tmp_path)])
    with pytest.raises(SystemExit):
        new.run_reconfigure(args)


def test_read_project_state_reconstructs_a_celery_project(tmp_path):
    from dsd_cloudron.packaging import CloudronAppConfig, render_all

    render_all(
        CloudronAppConfig(
            project_name="shop",
            app_id="com.example.shop",
            enable_celery=True,
            enable_redis=True,
        ),
        tmp_path,
    )
    state = new._read_project_state(tmp_path)
    assert state["enable_celery"] is True  # supervisor/celery-worker.conf present
    assert state["enable_redis"] is True


def test_reconfigure_config_rejects_an_impossible_reconstructed_state(tmp_path):
    import json

    from dsd_cloudron.packaging import CloudronAppConfig, render_all

    render_all(
        CloudronAppConfig(
            project_name="shop",
            app_id="com.example.shop",
            enable_celery=True,
            enable_redis=True,
        ),
        tmp_path,
    )
    # A celery worker on disk but the Redis addon deleted from the manifest is an
    # impossible state; CloudronAppConfig.__post_init__ rejects it and reconfigure_config
    # must translate that ValueError into a clean _fail (SystemExit), not a traceback.
    manifest_path = tmp_path / "CloudronManifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    del data["addons"]["redis"]
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    args = new.parse_args(["reconfigure", "--project-dir", str(tmp_path)])
    with pytest.raises(SystemExit):
        new.reconfigure_config(tmp_path, args)


def test_read_project_state_rejects_a_non_utf8_manifest(tmp_path):
    from dsd_cloudron.packaging import CloudronAppConfig, render_all

    # The manifest read must abort cleanly on non-UTF-8 bytes (a UnicodeDecodeError,
    # not JSONDecodeError), matching the retrofit/packaging sibling readers.
    render_all(
        CloudronAppConfig(project_name="shop", app_id="com.example.shop"), tmp_path
    )
    (tmp_path / "CloudronManifest.json").write_bytes(b"\xff\xfe not utf-8")
    with pytest.raises(SystemExit):
        new._read_project_state(tmp_path)


def test_read_project_state_rejects_a_non_object_manifest(tmp_path):
    from dsd_cloudron.packaging import CloudronAppConfig, render_all

    # A manifest that is valid JSON but a top-level array (not an object) must abort
    # cleanly before the `addons` lookup below would raise a raw error on it.
    render_all(
        CloudronAppConfig(project_name="shop", app_id="com.example.shop"), tmp_path
    )
    (tmp_path / "CloudronManifest.json").write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit):
        new._read_project_state(tmp_path)


def test_read_project_state_rejects_wrong_shape_addons(tmp_path):
    from dsd_cloudron.packaging import CloudronAppConfig, render_all

    # A valid-JSON manifest with addons set to null must abort cleanly rather than
    # raise a raw TypeError from the `"redis" in addons` reconstruction.
    render_all(
        CloudronAppConfig(project_name="shop", app_id="com.example.shop"), tmp_path
    )
    (tmp_path / "CloudronManifest.json").write_text(
        '{"addons": null}', encoding="utf-8"
    )
    with pytest.raises(SystemExit):
        new._read_project_state(tmp_path)


def test_read_project_state_missing_package_dir_fails_cleanly(tmp_path):
    from dsd_cloudron.packaging import CloudronAppConfig, render_all

    # Manifest present but the project package (its cloudron_settings.py) gone: the slug
    # cannot be detected, so it fails cleanly rather than reconstructing a wrong package.
    render_all(
        CloudronAppConfig(project_name="shop", app_id="com.example.shop"), tmp_path
    )
    (tmp_path / "shop" / "cloudron_settings.py").unlink()
    with pytest.raises(SystemExit):
        new._read_project_state(tmp_path)


def test_reconfigure_of_a_retrofit_without_sso_re_renders_byte_identically(
    tmp_path, monkeypatch
):
    from dsd_cloudron.packaging import CloudronAppConfig, render_all

    # A retrofit-no-SSO project ships no cloudron_adapters.py, so reconstruction reads
    # greenfield=True even though it was deployed greenfield=False. That misread is inert:
    # no artifact reads greenfield when SSO is off, so the re-render matches disk exactly
    # and reconfigure prompts for nothing. This pins the invariant the reconstruction
    # docstring rests on.
    render_all(
        CloudronAppConfig(
            project_name="shop", app_id="com.example.shop", greenfield=False
        ),
        tmp_path,
    )
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    prompted = []
    monkeypatch.setattr(
        "builtins.input", lambda prompt="": prompted.append(prompt) or "n"
    )
    args = new.parse_args(["reconfigure", "--project-dir", str(tmp_path)])
    new.run_reconfigure(args)
    assert prompted == []  # nothing differed, so nothing was prompted
    after = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert after == before
