from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_readme_documents_both_entry_points():
    text = (ROOT / "README.md").read_text()
    assert "manage.py deploy" in text          # retrofit
    assert "dsd-cloudron new" in text           # greenfield
    assert "cloudron install" in text
    assert "cloudron update" in text            # iteration loop


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
    assert "MIT" in readme.split("## License", 1)[-1]


def test_pyproject_declares_mit_without_license_classifier():
    # PEP 639: an SPDX license expression and a "License ::" classifier are
    # mutually exclusive; keeping both fails `python -m build`. Pin the resolved
    # state - MIT expression, no license classifier - since this is the one
    # surface the original BSD/MIT contradiction actually lived on.
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert 'license = "MIT"' in pyproject
    assert "License :: OSI Approved" not in pyproject
