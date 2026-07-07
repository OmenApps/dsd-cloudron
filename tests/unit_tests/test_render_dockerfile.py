from dsd_cloudron.packaging import CloudronAppConfig, render_dockerfile

BASE = "FROM cloudron/base:5.0.0@sha256:04fd70dbd8ad6149c19de39e35718e024417c3e01dc9c6637eaf4a41ec4e596c"


def _dockerfile(**kwargs):
    config = CloudronAppConfig(project_name="blog", app_id="com.example.blog", **kwargs)
    return render_dockerfile(config)


def test_final_stage_is_pinned_base():
    text = _dockerfile()
    # The pinned base must be the LAST FROM in the file (final build stage).
    from_lines = [ln for ln in text.splitlines() if ln.startswith("FROM ")]
    assert from_lines[-1] == BASE


def test_no_build_time_collectstatic():
    assert "collectstatic" not in _dockerfile()


def test_copies_runtime_artifacts():
    text = _dockerfile()
    assert "COPY supervisor/ /etc/supervisor/conf.d/" in text
    assert "COPY nginx.conf /app/pkg/nginx.conf" in text
    assert "COPY start.sh /app/pkg/start.sh" in text
    assert "RUN chmod +x /app/pkg/start.sh" in text
    assert 'CMD ["/app/pkg/start.sh"]' in text


def test_no_unrendered_template_sentinel():
    # The engine's string_if_invalid sentinel must never appear in output; its
    # presence means a template referenced an undefined context variable.
    assert "INVALID_TEMPLATE_VAR" not in _dockerfile()


def test_req_txt_install_block():
    text = _dockerfile(pkg_manager="req_txt")
    assert "COPY requirements.txt" in text
    # Retrofits install with uv from requirements.txt, not pip.
    assert "uv pip install" in text
    assert "-r /app/code/requirements.txt" in text


def test_retrofit_managers_share_one_dockerfile():
    # req_txt/poetry/pipenv all install from requirements.txt with uv, so they
    # render an identical Dockerfile; only the greenfield uv (pyproject) path differs.
    req_txt = _dockerfile(pkg_manager="req_txt")
    assert _dockerfile(pkg_manager="poetry") == req_txt
    assert _dockerfile(pkg_manager="pipenv") == req_txt
    assert _dockerfile(pkg_manager="uv") != req_txt


def test_uv_install_block():
    text = _dockerfile(pkg_manager="uv")
    assert "uv pip install" in text
    # The greenfield/uv path installs from pyproject.toml, not requirements.txt.
    assert "-r pyproject.toml" in text


def test_relocates_supervisord_log_off_readonly_layer():
    assert "logfile=/run/supervisord.log" in _dockerfile()


def test_install_block_not_html_escaped():
    # Regression guard: the install block is substituted as a {{ variable }} and
    # contains shell "&&". With autoescape on (the default for a hand-built
    # Context) it would become "&amp;&amp;" and break the build. Both surviving
    # blocks (requirements.txt and pyproject) must keep the operator verbatim.
    for manager in ("req_txt", "poetry", "pipenv", "uv"):
        text = _dockerfile(pkg_manager=manager)
        assert "&amp;" not in text
        assert "&& \\" in text


def test_no_settings_module_env_for_flat_settings():
    # A flat <project>/settings.py project needs no DJANGO_SETTINGS_MODULE pin -
    # wsgi/manage.py/celery already resolve <project>.settings - so the Dockerfile
    # stays byte-for-byte identical to the no-pin default.
    assert "ENV DJANGO_SETTINGS_MODULE" not in _dockerfile()
    assert "ENV DJANGO_SETTINGS_MODULE" not in _dockerfile(
        settings_module="blog.settings"
    )


def test_pins_split_settings_module_as_env():
    # A split-settings (Wagtail) project has the Cloudron gate appended to
    # settings/production.py while wsgi/manage.py/celery default to settings/dev.
    # Baking the module as an image ENV pins it for the supervisor process tree AND
    # for `cloudron exec` shells (where `manage.py changepassword admin` recovery
    # would otherwise load dev settings and hit SQLite on the read-only rootfs).
    text = _dockerfile(settings_module="blog.settings.production")
    assert 'ENV DJANGO_SETTINGS_MODULE="blog.settings.production"' in text
    # The ENV must precede the CMD so every runtime process (and exec shell) inherits it.
    assert text.index("ENV DJANGO_SETTINGS_MODULE") < text.index(
        'CMD ["/app/pkg/start.sh"]'
    )
