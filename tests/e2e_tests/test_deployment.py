"""Live deployment test. Skipped by default via collect_ignore in tests/conftest.py.

Run deliberately (use `python -m pytest`, NOT the bare `pytest` console script:
the bare script does not put the repo root on sys.path, and `tests/` is a
namespace package with no top-level __init__.py, so `import tests...` fails at
collection):
    CLOUDRON_E2E_LOCATION=dsd-e2e python -m pytest tests/e2e_tests/test_deployment.py -p no:cacheprovider
"""

from pathlib import Path

from . import utils  # relative import: resolves under either invocation


def test_greenfield_deploys(tmp_path, e2e_location):
    from dsd_cloudron import new

    args = new.parse_args(["new", "Dsd E2e", "--output-dir", str(tmp_path)])
    project_dir = Path(new.scaffold(args))

    try:
        utils.install(e2e_location, cwd=project_dir)
        logs = utils.app_logs(e2e_location).stdout
        # The deployed app must never leak real secret VALUES into logs. Asserting
        # on the variable name is theater - apps never print the name; a leak
        # prints the value (e.g. a settings dump or traceback). Read the actual
        # injected values and assert each is absent, plus the initial admin
        # password file written by start.sh.
        env = utils.app_env(e2e_location)
        secret_values = [
            env.get("CLOUDRON_POSTGRESQL_PASSWORD", ""),
            env.get("CLOUDRON_REDIS_URL", ""),
        ]
        for value in secret_values:
            if value:
                assert value not in logs
        admin_pw = utils.run(
            f"cloudron exec --app {e2e_location} -- cat /app/data/.initial_admin_password"
        ).stdout.strip()
        if admin_pw:
            assert admin_pw not in logs
    finally:
        utils.uninstall(e2e_location)
