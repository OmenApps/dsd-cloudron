from dsd_cloudron.packaging import (
    CloudronAppConfig,
    render_dockerfile,
    render_start_sh,
    render_cloudron_settings,
    render_supervisor_confs,
    render_nginx_conf,
    render_readme,
    render_celery_app,
)

PINNED_BASE = "FROM cloudron/base:5.0.0@sha256:04fd70dbd8ad6149c19de39e35718e024417c3e01dc9c6637eaf4a41ec4e596c"


def _full():
    return CloudronAppConfig(
        project_name="blog",
        app_id="com.example.blog",
        enable_redis=True,
        enable_celery=True,
        enable_sendmail=True,
        enable_sso=True,
    )


def test_invariant_final_stage_pinned_base():
    from_lines = [
        ln for ln in render_dockerfile(_full()).splitlines() if ln.startswith("FROM ")
    ]
    assert from_lines[-1] == PINNED_BASE


def test_invariant_secret_key_own_marker_and_initialized_marker():
    text = render_start_sh(_full())
    assert "/app/data/.secret_key" in text
    assert "/app/data/.initialized" in text


def test_invariant_drop_privileges_and_exec():
    text = render_start_sh(_full())
    assert "chown -R cloudron:cloudron /app/data" in text
    assert text.rstrip().endswith("--nodaemon")
    assert "exec /usr/bin/supervisord" in text


def test_invariant_settings_gated_on_cloudron_app_origin():
    assert 'if os.environ.get("CLOUDRON_APP_ORIGIN"):' in render_cloudron_settings(
        _full()
    )


def test_invariant_all_output_to_stdio_no_rotation():
    for contents in render_supervisor_confs(_full()).values():
        assert "stdout_logfile_maxbytes=0" in contents
        assert "stderr_logfile_maxbytes=0" in contents


def test_invariant_oidc_guarded_on_issuer_presence():
    assert 'os.environ.get("CLOUDRON_OIDC_ISSUER")' in render_cloudron_settings(_full())


def test_invariant_plain_http_no_tls_in_nginx():
    text = render_nginx_conf(_full())
    assert "ssl" not in text.lower()
    assert "listen 8000;" in text


def test_invariant_no_unrendered_template_vars():
    # The standalone Engine uses string_if_invalid="INVALID_TEMPLATE_VAR[%s]", so
    # any template/context drift (an undefined variable) shows up as the sentinel
    # rather than a silent empty string. No rendered artifact may contain it.
    config = _full()
    rendered = [
        render_dockerfile(config),
        render_start_sh(config),
        render_nginx_conf(config),
        render_readme(config),
        render_celery_app(config),
    ] + list(render_supervisor_confs(config).values())
    for text in rendered:
        assert "INVALID_TEMPLATE_VAR" not in text
