"""Execute the rendered start.sh to verify shell semantics substring matching can't.

start.sh hardcodes absolute roots (/app/data, /app/code, /run, and the
supervisord paths), its only template variable is {{ project_name }}, and it runs
under `set -eu` as root. So there is nothing to "template": the harness rewrites
the rendered TEXT to relocate those roots under a tmp sandbox, stubs manage.py
and the gosu/chown binaries, and runs `bash start.sh`. That lets us assert the
things a substring check cannot: the secret-key temp+mv and chmod 600, key
idempotency, admin-password retry-safety and auto-delete, that a failed migrate
emits the MIGRATE_FAILED marker and aborts before the first-run bootstrap, and that
start.sh's recursive chown deliberately excludes /app/data/custom_settings.py (whose
owner is the trust signal the settings gate reads).
"""

import os
import shlex
import stat
import subprocess

from dsd_cloudron.packaging import CloudronAppConfig, render_start_sh

# The one line the harness must neutralize: launching a real supervisord would
# never return. It is the sole occurrence of the /usr/bin and /etc/supervisor
# literals, so replacing it also removes the only paths outside the sandbox.
_EXEC_LINE = (
    "exec /usr/bin/supervisord --configuration "
    "/etc/supervisor/supervisord.conf --nodaemon"
)

_GOSU_SHIM = '#!/bin/bash\n# Drop the leading cloudron:cloudron arg and run the rest.\nshift\nexec "$@"\n'


def _relocate(script, root):
    """Rewrite start.sh's absolute roots under `root` and neutralize the exec line.

    Replace /run before /app/ so the two passes stay disjoint. This is safe even
    when `root` itself contains "/run" or "/app" (e.g. TMPDIR=/run/user/<uid> on a
    systemd host): str.replace makes a single left-to-right pass and never
    re-scans what it inserted, and the same `root` string is spliced into both the
    script and the test's expected paths, so any /run|/app inside it stays inert
    and internally consistent. The /app/ replacement (with its trailing slash)
    rewrites /app/data, /app/code, and the /app/data/custom_settings.py prune path
    in one pass.
    """
    script = script.replace(_EXEC_LINE, 'echo "==> supervisor start stubbed"')
    script = script.replace("/run", f"{root}/run")
    script = script.replace("/app/", f"{root}/app/")
    return script


class _Harness:
    """A relocated start.sh plus the stub binaries/files it needs to run offline."""

    def __init__(self, tmp_path, with_custom_settings=True):
        self.data = tmp_path / "app" / "data"
        self.code = tmp_path / "app" / "code"
        self.chown_log = tmp_path / "chown.log"

        # app/data must exist so we can drop custom_settings.py before the run; the
        # script's own `mkdir -p` (idempotent) recreates the rest.
        self.data.mkdir(parents=True)
        # A plain regular file at the pruned path drives the find/prune branch;
        # omitting it drives the recursive else branch (the no-override case).
        # Ownership is irrelevant - the prune is path-based - so a test-user-owned
        # file exercises the exclusion.
        if with_custom_settings:
            (self.data / "custom_settings.py").write_text(
                "SECRET = 1\n", encoding="utf-8"
            )

        # manage.py is invoked as `python3 <abs>/manage.py <cmd>`, so it is real
        # Python (a #!/bin/bash stub would be parsed as Python). It is argv-aware:
        # collectstatic/migrate always succeed; createsuperuser fails only when the
        # toggle env var is set, exercising the retry branch.
        (self.code).mkdir(parents=True)
        (self.code / "manage.py").write_text(
            "import os, sys\n"
            'command = sys.argv[1] if len(sys.argv) > 1 else ""\n'
            'if command == "createsuperuser" and os.environ.get("FAIL_CREATESUPERUSER"):\n'
            "    sys.exit(1)\n"
            'if command == "migrate" and os.environ.get("FAIL_MIGRATE"):\n'
            "    sys.exit(1)\n"
            "sys.exit(0)\n",
            encoding="utf-8",
        )
        # venv/bin/activate is `source`d under `set -e`; an empty file is enough.
        activate = self.code / "venv" / "bin" / "activate"
        activate.parent.mkdir(parents=True)
        activate.write_text("", encoding="utf-8")

        # PATH shims. gosu passes through; chown records its args then exits 0 (a
        # real chown cloudron:cloudron as a non-root test user would fail and, under
        # set -e, abort the harness - recording-and-exit-0 is the whole point).
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        self._write_exec(self.bin / "gosu", _GOSU_SHIM)
        self._write_exec(
            self.bin / "chown",
            f'#!/bin/bash\nprintf "%s\\n" "$@" >> "{self.chown_log}"\nexit 0\n',
        )

        self.script = tmp_path / "start.sh"
        rendered = render_start_sh(
            CloudronAppConfig(project_name="blog", app_id="com.example.blog")
        )
        self.script.write_text(_relocate(rendered, tmp_path), encoding="utf-8")

    @staticmethod
    def _write_exec(path, contents):
        path.write_text(contents, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def run(self, fail_createsuperuser=False, fail_migrate=False, expect_success=True):
        env = dict(os.environ)
        env["PATH"] = f"{self.bin}{os.pathsep}{env['PATH']}"
        # Set both toggles explicitly so an inherited value from the caller's shell
        # cannot flip a success run into a failure one.
        if fail_createsuperuser:
            env["FAIL_CREATESUPERUSER"] = "1"
        else:
            env.pop("FAIL_CREATESUPERUSER", None)
        if fail_migrate:
            env["FAIL_MIGRATE"] = "1"
        else:
            env.pop("FAIL_MIGRATE", None)
        # Pin a permissive umask (022) before running the script, so a plain redirect
        # leaves a 0o644 file and the explicit `chmod 600` is provably what tightens the
        # secret/password files to 0o600. Without this, a restrictive ambient umask (077)
        # would already yield 0o600 and mask a regression that dropped the chmod.
        result = subprocess.run(
            ["bash", "-c", f"umask 0022; exec bash {shlex.quote(str(self.script))}"],
            env=env,
            capture_output=True,
            text=True,
        )
        if expect_success:
            assert result.returncode == 0, result.stderr
        return result

    def chown_lines(self):
        if not self.chown_log.exists():
            return []
        return self.chown_log.read_text(encoding="utf-8").splitlines()


def _mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_secret_key_written_600_and_stable(tmp_path):
    harness = _Harness(tmp_path)
    harness.run()
    key = harness.data / ".secret_key"
    assert key.exists()
    assert _mode(key) == 0o600
    first = key.read_text(encoding="utf-8")
    assert first.strip()  # a non-empty token, not a zero-byte file
    # The atomic temp+mv completed: no half-written .secret_key.tmp is left behind
    # on the persistent volume for a later boot to trip over.
    assert not (harness.data / ".secret_key.tmp").exists()

    # A second start must reuse the persisted key byte-for-byte (the -s guard), so
    # SECRET_KEY does not rotate and invalidate every session on each restart.
    harness.run()
    assert key.read_text(encoding="utf-8") == first


def test_admin_password_written_600_then_auto_removed(tmp_path):
    harness = _Harness(tmp_path)
    harness.run()  # first run: createsuperuser succeeds, .initialized is written
    password = harness.data / ".initial_admin_password"
    assert password.exists()
    assert _mode(password) == 0o600
    assert (harness.data / ".initialized").exists()

    # Next start: initialized + password both present, so the bootstrap secret is
    # dropped rather than riding along in every backup.
    harness.run()
    assert not password.exists()


def test_admin_password_retried_with_same_value_when_superuser_fails(tmp_path):
    harness = _Harness(tmp_path)
    harness.run(fail_createsuperuser=True)
    password = harness.data / ".initial_admin_password"
    assert password.exists()
    assert not (harness.data / ".initialized").exists()  # not marked done on failure
    first = password.read_text(encoding="utf-8")

    # A failed first run must keep the app retryable: the password file is reused
    # (the -s guard), not regenerated, so the operator's saved value stays valid.
    harness.run(fail_createsuperuser=True)
    assert not (harness.data / ".initialized").exists()
    assert password.read_text(encoding="utf-8") == first


def test_custom_settings_excluded_from_ownership_normalization(tmp_path):
    harness = _Harness(tmp_path)
    harness.run()
    lines = harness.chown_lines()
    custom = str(harness.data / "custom_settings.py")
    media = str(harness.data / "media")
    # `media in lines` is load-bearing: the chown stub does not recurse, so a
    # regression to a plain `chown -R /app/data` would log only the /app/data root
    # and never the enumerated `media` child - this assertion is what proves the
    # find/prune branch ran and not a re-chown that would sweep in custom_settings.
    assert media in lines
    # custom_settings.py was never handed to chown, so its owner (the trust signal
    # the settings gate reads) survives every restart.
    assert custom not in lines


def test_ownership_normalization_recurses_without_custom_settings(tmp_path):
    # No override file present: start.sh takes the common branch and chowns the
    # whole data volume recursively in one call. Exercising this else arm guards
    # the branch the find/prune test bypasses.
    harness = _Harness(tmp_path, with_custom_settings=False)
    harness.run()
    lines = harness.chown_lines()
    # The data dir is handed to `chown -R` as a single target...
    assert str(harness.data) in lines
    # ...not the find/prune branch, which would instead list children one per line.
    assert str(harness.data / "media") not in lines


def test_migrate_failure_emits_marker_and_aborts(tmp_path):
    harness = _Harness(tmp_path)
    result = harness.run(fail_migrate=True, expect_success=False)
    assert result.returncode != 0
    assert "==> MIGRATE_FAILED" in result.stderr
    # start.sh aborts at migrate, before the first-run admin bootstrap.
    assert not (harness.data / ".initialized").exists()
