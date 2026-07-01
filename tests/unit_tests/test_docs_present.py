from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_readme_documents_both_entry_points():
    text = (ROOT / "README.md").read_text()
    assert "manage.py deploy" in text  # retrofit
    assert "dsd-cloudron new" in text  # greenfield
    assert "cloudron install" in text
    assert "cloudron update" in text  # iteration loop


def test_license_and_changelog_exist():
    assert (ROOT / "LICENSE").read_text().strip()
    assert (ROOT / "CHANGELOG.md").read_text().strip()


def test_license_name_agrees_between_license_and_readme():
    # The license family must match across LICENSE and the README's license
    # section so the two cannot drift (the repo already had a BSD classifier
    # over an MIT file). "MIT" is the resolved choice.
    license_text = (ROOT / "LICENSE").read_text()
    readme = (ROOT / "README.md").read_text()
    assert "MIT License" in license_text
    # Check the README's license section specifically; the split fallback would
    # otherwise return the whole file if the heading were ever removed, letting
    # a stray "MIT" anywhere pass for a section that no longer exists.
    parts = readme.split("## License", 1)
    assert len(parts) == 2, "README is missing a '## License' section"
    assert "MIT" in parts[1]


def test_pyproject_declares_mit_without_license_classifier():
    # PEP 639: an SPDX license expression and a "License ::" classifier are
    # mutually exclusive; keeping both fails `python -m build`. Pin the resolved
    # state - MIT expression, no license classifier - since this is the one
    # surface the original BSD/MIT contradiction actually lived on.
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert 'license = "MIT"' in pyproject
    # setuptools>=77 errors when an SPDX `license` expression coexists with ANY
    # `License ::` classifier, not only the OSI-approved family, so assert the
    # broad condition that actually breaks `python -m build`.
    assert "License ::" not in pyproject


def test_pyproject_scopes_pytest_to_tests_dir():
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert "[tool.pytest.ini_options]" in pyproject
    assert 'testpaths = ["tests"]' in pyproject
    assert (
        "skip_auto_dsd_call" in pyproject
    )  # marker registered, no PytestUnknownMarkWarning


def test_contributing_doc_covers_test_tiers():
    text = (ROOT / "CONTRIBUTING.md").read_text()
    for token in (
        "unit_tests",
        "integration_tests",
        "bake_tests",
        "e2e_tests",
        "python -m pytest",
        "black",
    ):
        assert token in text


def test_pyproject_lists_supported_django_versions():
    # Advertise only the Django versions a durable CI leg pins (the LTS releases
    # and the current major). Do not claim the non-LTS 5.0/5.1: no CI leg exercises
    # them and they are past upstream support. Pin the set both ways so neither an
    # unadvertised-but-tested nor an advertised-but-untested drift can recur.
    pyproject = (ROOT / "pyproject.toml").read_text()
    for version in ("4.2", "5.2", "6.0"):
        assert f"Framework :: Django :: {version}" in pyproject
    for version in ("5.0", "5.1"):
        assert f"Framework :: Django :: {version}" not in pyproject
