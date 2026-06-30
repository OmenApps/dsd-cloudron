"""Helpers for a real Cloudron deploy. Used only by the e2e harness."""

import shlex
import subprocess


def run(cmd, cwd=None):
    """Run a command, return CompletedProcess; raise on non-zero."""
    result = subprocess.run(shlex.split(cmd), cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{cmd} failed:\n{result.stdout}\n{result.stderr}")
    return result


def install(location, cwd):
    return run(f"cloudron install -l {location}", cwd=cwd)


def uninstall(location):
    return run(f"cloudron uninstall --app {location}")


def app_logs(location):
    return run(f"cloudron logs --app {location}")


def app_env(location):
    """Return the deployed app's runtime environment as a {name: value} dict.

    Used to assert that real secret *values* (not just their variable names) do
    not appear in the logs. `cloudron exec` runs a command inside the app.
    """
    out = run(f"cloudron exec --app {location} -- env").stdout
    env = {}
    for line in out.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            env[key] = value
    return env
