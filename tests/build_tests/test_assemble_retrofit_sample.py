"""Offline checks that the retrofit build-context assembler produces a
buildable requirements.txt-shape project. No Docker here; the build itself is
exercised by the CI build job."""

import subprocess
import sys
from pathlib import Path

from tests.build_tests.assemble_retrofit_sample import assemble_retrofit_sample

_SCRIPT = Path(__file__).with_name("assemble_retrofit_sample.py")


def _lower_bound(spec):
    """Zero-padded numeric tuple for the lower bound of a `>=X.Y.Z` pin."""
    digits = [int(part) for part in spec.split(".") if part.isdigit()]
    return tuple(digits)


def _at_least(pinned, floor):
    p, f = list(_lower_bound(pinned)), list(_lower_bound(floor))
    width = max(len(p), len(f))
    p += [0] * (width - len(p))
    f += [0] * (width - len(f))
    return p >= f


def test_dockerfile_is_requirements_shape(tmp_path):
    assemble_retrofit_sample(tmp_path)
    dockerfile = (tmp_path / "Dockerfile").read_text()
    assert "COPY requirements.txt /app/code/requirements.txt" in dockerfile
    assert "pyproject.toml" not in dockerfile


def test_writes_buildable_project_and_artifacts(tmp_path):
    assemble_retrofit_sample(tmp_path)
    assert (tmp_path / "manage.py").exists()
    assert (tmp_path / "requirements.txt").exists()
    assert (tmp_path / "CloudronManifest.json").exists()
    assert (tmp_path / "start.sh").exists()
    settings = (tmp_path / "smoke" / "settings.py").read_text()
    # The Cloudron import must be the LAST statement: cloudron_settings overrides
    # DATABASES/STATIC_ROOT/etc, so anything defined after it would silently win
    # over the Cloudron config at runtime. Assert position, not just presence.
    assert settings.rstrip().endswith(
        "from .cloudron_settings import *  # noqa: E402,F401,F403"
    )
    assert (tmp_path / "smoke" / "cloudron_settings.py").exists()


def test_requirements_carry_runtime_deps(tmp_path):
    assemble_retrofit_sample(tmp_path)
    reqs = (tmp_path / "requirements.txt").read_text()
    for pkg in ("Django", "gunicorn", "psycopg[binary]", "django-redis"):
        assert pkg in reqs


def test_root_path_served_for_health_check(tmp_path):
    assemble_retrofit_sample(tmp_path)
    urls = (tmp_path / "smoke" / "urls.py").read_text()
    assert 'path("", health)' in urls


def test_requirements_meet_deployer_floors(tmp_path):
    """The fixture's pins must not fall below the deployer's own security/compat
    floors, so this build cell cannot ship weaker dependencies than a real
    retrofit deploy - and the two cannot silently drift apart."""
    from dsd_cloudron.platform_deployer import _REQUIREMENT_FLOORS, _bare_name

    assemble_retrofit_sample(tmp_path)
    pinned = {}
    for line in (tmp_path / "requirements.txt").read_text().splitlines():
        line = line.strip()
        if not line or ">=" not in line:
            continue
        pinned[_bare_name(line)] = line.split(">=", 1)[1].strip()

    for package, floor in _REQUIREMENT_FLOORS.items():
        if package in pinned:
            assert _at_least(pinned[package], floor.lstrip(">=")), (
                f"{package} pinned at >={pinned[package]} is below the deployer "
                f"floor {floor}"
            )


def test_cli_usage_error_without_target_dir():
    """The __main__ guard is what the CI build job invokes as a script; a missing
    argument must exit 2 with a usage message, not silently do nothing."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "usage:" in result.stderr
