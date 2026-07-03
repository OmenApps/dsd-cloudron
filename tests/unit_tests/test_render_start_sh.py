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


def test_secret_key_written_atomically():
    # Guard on non-empty and write via temp+mv so an interrupted first boot
    # cannot persist a zero-byte key file that bricks every later start.
    text = _start()
    assert "[[ ! -s /app/data/.secret_key ]]" in text
    assert "mv /app/data/.secret_key.tmp /app/data/.secret_key" in text
    # The secret file must not be world/group readable.
    assert "chmod 600 /app/data/.secret_key.tmp" in text


def test_activates_virtualenv_before_management_commands():
    text = _start()
    assert 'source "${CODE}/venv/bin/activate"' in text


def test_collectstatic_and_migrate_every_start():
    text = _start()
    assert "collectstatic --noinput" in text
    assert "migrate --noinput" in text


def test_first_run_superuser_behind_initialized_marker():
    text = _start()
    assert "/app/data/.initialized" in text
    assert "createsuperuser" in text
    assert "--username admin" in text
    assert "changeme123" not in text
    # The generated-password file is written (via .tmp) and read by createsuperuser.
    assert "/app/data/.initial_admin_password.tmp" in text
    assert "/app/data/.initial_admin_password" in text
    # Mirror the secret-key guards: assert the password is generated (not a
    # constant) and written mode 600, so a future edit cannot quietly drop the
    # randomness or the permission bits with only the golden re-pinned.
    assert "secrets.token_urlsafe(18)" in text
    assert "chmod 600 /app/data/.initial_admin_password.tmp" in text
    # The marker is written only after createsuperuser succeeds, so a failed
    # first run retries instead of leaving the app with no admin account.
    assert "touch /app/data/.initialized" in text
    assert text.index("touch /app/data/.initialized") > text.index("createsuperuser")


def test_superuser_password_not_exported_to_long_lived_env():
    # The default password must be scoped to the createsuperuser command, not
    # exported into the shell that later execs supervisord.
    text = _start()
    assert "export DJANGO_SUPERUSER_PASSWORD" not in text


def test_initial_admin_password_file_removed_after_init():
    # Once .initialized exists (the first run succeeded), the one-time password
    # file is removed on the next start so it stops riding along in every backup.
    text = _start()
    assert "rm -f /app/data/.initial_admin_password" in text
    # The cleanup is guarded on .initialized so a failed first run (which leaves
    # .initialized absent) keeps the file for the retry.
    cleanup = text.index("rm -f /app/data/.initial_admin_password")
    guard = text.rindex("/app/data/.initialized", 0, cleanup)
    assert guard != -1
    # It runs BEFORE the first-run block, not inside it (inside, .initialized can
    # never exist, so it would never fire).
    first_run = text.index("First run: creating default admin superuser")
    assert cleanup < first_run


def test_chown_and_exec_supervisord():
    text = _start()
    # The common no-override case keeps the cheap recursive chown of /app/data.
    assert "chown -R cloudron:cloudron /app/data" in text
    assert "gosu cloudron:cloudron" in text
    assert text.rstrip().endswith(
        "exec /usr/bin/supervisord --configuration /etc/supervisor/supervisord.conf --nodaemon"
    )


def test_chown_excludes_custom_settings():
    # When a custom_settings.py is present its ownership is the settings gate's
    # trust signal, so start.sh must NOT re-chown it (that would launder an
    # attacker-dropped, cloudron-owned file into a root-owned, exec'd one). The
    # find branch prunes it and uses chown -h so a symlink argument under /app/data
    # is never dereferenced.
    text = _start()
    assert "-path /app/data/custom_settings.py -prune" in text
    assert "chown -h cloudron:cloudron" in text
