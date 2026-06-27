from dsd_cloudron.packaging import CloudronAppConfig, render_start_sh


def _start(**kwargs):
    config = CloudronAppConfig(project_name="blog", app_id="com.example.blog", **kwargs)
    return render_start_sh(config)


def test_shebang_and_strict_mode():
    text = _start()
    assert text.startswith("#!/bin/bash\n")
    assert "set -eu" in text


def test_secret_key_own_marker_and_export():
    text = _start()
    assert "/app/data/.secret_key" in text
    assert "secrets.token_urlsafe(64)" in text
    assert 'export SECRET_KEY="$(cat /app/data/.secret_key)"' in text


def test_collectstatic_and_migrate_every_start():
    text = _start()
    assert "collectstatic --noinput" in text
    assert "migrate --noinput" in text


def test_first_run_superuser_behind_initialized_marker():
    text = _start()
    assert "/app/data/.initialized" in text
    assert "createsuperuser" in text
    assert "admin" in text
    assert "changeme123" in text


def test_chown_and_exec_supervisord():
    text = _start()
    assert "chown -R cloudron:cloudron /app/data" in text
    assert "gosu cloudron:cloudron" in text
    assert text.rstrip().endswith(
        "exec /usr/bin/supervisord --configuration /etc/supervisor/supervisord.conf --nodaemon"
    )
