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


def test_dockerignore_excludes_next_steps_file():
    # CLOUDRON_NEXT_STEPS.md is written next to the project on each deploy; keep it
    # out of the image build context (the Dockerfile does COPY . /app/code/).
    text = render_dockerignore(_config())
    assert "CLOUDRON_NEXT_STEPS.md" in text


def test_readme_greenfield_sso_claims_allauth_wired():
    # A greenfield --sso project ships allauth fully wired, so the readme may say so.
    text = render_readme(_config(enable_sso=True, greenfield=True))
    assert "fully wired" in text
    assert "NOT auto-wired" not in text


def test_readme_retrofit_sso_says_allauth_not_auto_wired():
    # The retrofit --sso path renders the provider block but does NOT wire allauth
    # into the user's project; the readme must say so and point at the follow-up.
    text = render_readme(_config(enable_sso=True, greenfield=False))
    assert "NOT auto-wired" in text
    assert "CLOUDRON_NEXT_STEPS.md" in text
    assert "fully wired" not in text


def test_readme_without_sso_makes_no_wiring_claim():
    # No --sso, either mode: the readme carries no allauth wiring claim at all.
    for greenfield in (True, False):
        text = render_readme(_config(enable_sso=False, greenfield=greenfield))
        assert "fully wired" not in text
        assert "NOT auto-wired" not in text
