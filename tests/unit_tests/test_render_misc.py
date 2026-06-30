from dsd_cloudron.packaging import (
    CloudronAppConfig,
    render_dockerignore,
    render_readme,
)


def _config(**kwargs):
    return CloudronAppConfig(project_name="blog", app_id="com.example.blog", **kwargs)


def test_readme_documents_control_surface():
    text = render_readme(_config())
    assert "CloudronManifest.json" in text
    assert "cloudron_settings.py" in text
    assert "healthCheckPath" in text
    # The 2xx health-check requirement must be called out explicitly.
    assert "2xx" in text or "200" in text


def test_readme_mentions_iteration_loop():
    text = render_readme(_config())
    assert "cloudron update" in text
    assert "cloudron logs" in text


def test_readme_documents_first_signin_credential():
    # The manifest's postInstallMessage points operators here, so the generated
    # admin credential and the backup-residue cleanup step must be documented.
    text = render_readme(_config())
    assert "/app/data/.initial_admin_password" in text
    assert "cloudron exec" in text


def test_dockerignore_excludes_vcs_and_venv():
    text = render_dockerignore(_config())
    assert ".git" in text
    assert "venv" in text or ".venv" in text
    assert "__pycache__" in text
