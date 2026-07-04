"""Guards that the data files `dsd-cloudron new` reads at runtime actually ship.

Every other test runs against the source tree, so a packaging regression - an
explicit `[tool.setuptools.package-data]` that misses a glob, dropping
`include-package-data`, or moving a directory - would pass the suite while
breaking `dsd-cloudron new` for anyone who installed the wheel. These checks
resolve paths relative to the imported package (the source tree under an editable
install, site-packages under a wheel install), so they hold in both.
"""

from pathlib import Path

import dsd_cloudron

PKG_ROOT = Path(dsd_cloudron.__file__).parent
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_project_template_ships_with_package():
    # new.py resolves TEMPLATE_DIR as Path(__file__).parent / "project_template";
    # the cookiecutter scaffold reads it at runtime.
    template_dir = PKG_ROOT / "project_template"
    assert template_dir.is_dir(), (
        f"project_template/ missing at {template_dir}. "
        "Check pyproject.toml include-package-data and MANIFEST.in."
    )
    assert (template_dir / "cookiecutter.json").exists()


def test_extension_less_templates_ship_with_package():
    # settings_import and celery_app have no extension; a naive "*.conf"/"*.sh"
    # package-data glob would silently drop them from the wheel.
    templates_dir = PKG_ROOT / "templates"
    for name in ("settings_import", "celery_app", "cloudron_adapters"):
        assert (
            templates_dir / name
        ).exists(), (
            f"templates/{name} not found. Check MANIFEST.in and package-data config."
        )


def test_manifest_in_covers_critical_paths():
    manifest = (REPO_ROOT / "MANIFEST.in").read_text()
    assert "recursive-include dsd_cloudron/project_template" in manifest
    assert "recursive-include dsd_cloudron/templates" in manifest
