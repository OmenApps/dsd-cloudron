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


def test_migrate_failure_emits_marker():
    text = _start()
    # The marker is emitted from inside the migrate guard, so it must sit after the
    # migrate call and before the one-time admin bootstrap (the .initialized block); a
    # positional check catches a marker accidentally moved out of that guard, which a
    # bare presence check would not.
    assert "==> MIGRATE_FAILED" in text
    assert text.index("migrate --noinput") < text.index("==> MIGRATE_FAILED")
    assert text.index("==> MIGRATE_FAILED") < text.index("/app/data/.initialized")


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


def test_initial_admin_password_retired_only_on_acknowledgement():
    # The one-time password file is retired only once the operator acknowledges they
    # have it (the .acknowledged marker they touch via `cloudron exec`), never by
    # restart count - coupling deletion to restarts strands it, because image updates
    # and health-check restarts start a fresh container before an operator can read
    # it. The delete clears the marker alongside the file so a later re-init
    # re-announces a fresh password instead of deleting it against a stale ack.
    text = _start()
    delete = (
        "rm -f /app/data/.initial_admin_password "
        "/app/data/.initial_admin_password.acknowledged"
    )
    assert delete in text
    # The delete is guarded on the acknowledgement marker. rfind returns -1 (not a
    # ValueError) when the guard is absent, so the assertion can actually fail.
    guard = text.rfind(
        "/app/data/.initial_admin_password.acknowledged", 0, text.index(delete)
    )
    assert guard != -1
    # While the file is present and unacknowledged, every boot reprints the retrieve
    # + acknowledge steps - but never the password value itself.
    assert "cat /app/data/.initial_admin_password" in text
    assert "touch /app/data/.initial_admin_password.acknowledged" in text
    # Retirement runs AFTER the first-run block (it depends on the file + marker, not
    # on .initialized), so the reminder fires on the very boot that creates the file.
    first_run = text.index("First run: creating default admin superuser")
    assert text.index("A generated admin password is stored on the server") > first_run


def test_chown_and_exec_supervisord():
    text = _start()
    # The common no-override case keeps the cheap recursive chown of /app/data.
    assert "chown -R cloudron:cloudron /app/data" in text
    assert "gosu cloudron:cloudron" in text
    assert text.rstrip().endswith(
        "exec /usr/bin/supervisord --configuration /etc/supervisor/supervisord.conf --nodaemon"
    )


def test_start_sh_never_exports_settings_module():
    # The DJANGO_SETTINGS_MODULE pin lives in the Dockerfile as an ENV (so a
    # `cloudron exec` shell inherits it too, not just the supervisor process tree
    # a start.sh export would reach); see test_render_dockerfile.py. start.sh must
    # carry no export in either the flat or the split-settings case.
    assert "export DJANGO_SETTINGS_MODULE" not in _start()
    assert "export DJANGO_SETTINGS_MODULE" not in _start(
        settings_module="blog.settings"
    )
    assert "export DJANGO_SETTINGS_MODULE" not in _start(
        settings_module="blog.settings.production"
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


def test_wagtail_flag_syncs_default_site_after_migrate():
    # With --wagtail, start.sh repoints the default Wagtail Site at the deployed host
    # on every boot. page.full_url, canonical, og:url, and sitemap.xml derive from the
    # Site record, not WAGTAILADMIN_BASE_URL, so a fresh install would otherwise emit
    # the localhost:80 seed. The host is read back from WAGTAILADMIN_BASE_URL, which
    # cloudron_settings.py sets from CLOUDRON_APP_ORIGIN.
    text = _start(enable_wagtail=True)
    assert "is_default_site=True" in text
    assert "settings.WAGTAILADMIN_BASE_URL" in text
    # Instance .save() (not a queryset .update()) so Wagtail's post_save signal clears
    # the cached site root paths a bare UPDATE would leave stale.
    assert "site.save()" in text
    # It must run after migrate (the Site table has to exist) and before the one-time
    # admin bootstrap, so it sits inside neither the migrate guard nor the
    # .initialized block.
    assert text.index("migrate --noinput") < text.index("is_default_site=True")
    assert text.index("is_default_site=True") < text.index("/app/data/.initialized")


def test_no_wagtail_site_sync_without_flag():
    # The plain (non-Wagtail) start.sh must not carry the Site-sync block at all. The
    # golden snapshot pins the exact byte-for-byte equality with the pre-change
    # script; this guards the intent in a way a re-pinned golden alone would not.
    text = _start()
    assert "is_default_site" not in text
    assert "WAGTAILADMIN_BASE_URL" not in text
    assert "Wagtail Site" not in text
