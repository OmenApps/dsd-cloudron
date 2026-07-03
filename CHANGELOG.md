# Changelog

## 0.1.0 - unreleased

Initial release.

- Retrofit: `manage.py deploy` configures an existing Django project for Cloudron.
- Greenfield: `dsd-cloudron new` scaffolds a Cloudron-ready Django project.
- Batteries-included artifact set: PostgreSQL, Redis, Celery, sendmail, OIDC SSO,
  nginx + gunicorn, rendered through one packaging core.
- On-server build via `cloudron install` / `cloudron update`.

Verified on a real Cloudron server (8.0.2): a `--sso` install completes the OIDC
login round-trip against the `/accounts/oidc/cloudron/login/callback/` redirect
URI; a `--celery` install brings up the worker and beat, connects to the Redis
broker, and keeps its schedule under `/app/data`; `cloudron update` redeploys
while `/app/data` and the addons persist and `migrate` runs on every start.

Hardening fixes found during that verification:

- Give the manifest a default `author`; Cloudron rejects an empty author at install.
- Point the supervisor process `HOME` at a writable `/tmp`, since `/home/cloudron`
  is read-only and made gunicorn log a control-socket error on every start.
- Serve a home page at `/` so a bare visit and the post-login redirect resolve
  instead of returning a 404.

Artifact trust and security hardening:

- The generated `README-cloudron.md` now tells retrofit `--sso` users the truth:
  django-allauth is added to requirements but NOT auto-wired into their project,
  with a pointer to the follow-up steps and a note to close local self-service
  signup. Each deploy also writes a `CLOUDRON_NEXT_STEPS.md` operator aid next to
  the project with the change summary and follow-up notes.
- Harden the generated artifacts: nginx now sets `X-Forwarded-Proto https`
  literally instead of reflecting the inbound header (the one value
  `SECURE_PROXY_SSL_HEADER` trusts); `.dockerignore` excludes common secret files
  (`*.pem`, `*.key`, `local_settings.py`, `.env.*`, service-account JSON, `*.har`)
  so they cannot bake into an image layer; the Cloudron settings pin
  `SECURE_CONTENT_TYPE_NOSNIFF` and `SECURE_REFERRER_POLICY = "same-origin"`.
- Scaffolded `--sso` projects no longer accept local self-service signup: a
  generated account adapter closes `/accounts/signup/` so Cloudron OIDC is the
  only way in, while a social adapter keeps first-login OIDC provisioning working.
  Login, logout, password reset, and MFA stay available.
- The generated `cloudron_settings.py` now executes `/app/data/custom_settings.py`
  only when it is owned by `root` and not group/other-writable, so a file the app
  process could write itself can no longer become persistent code execution.
  BREAKING for existing installs: an override created with the old
  `cloudron push` recipe is `cloudron`-owned and stops applying until it is
  re-created inside a root `cloudron exec` shell as `root:cloudron` mode 640 (a
  file whose ownership came back non-root after a backup restore or app clone is
  skipped the same way). A rejected-but-present file logs a skip line to stderr.
- The one-time `/app/data/.initial_admin_password` file is now removed
  automatically on the first start after initialization, so the bootstrap secret
  no longer persists in every backup. Read it during the first-boot window;
  operators of existing installs should note that after their next restart the
  file is gone (reset with `manage.py changepassword admin` via `cloudron exec`).
