# Changelog

## 0.1.0 - unreleased

Initial release.

- Retrofit: `manage.py deploy` configures an existing Django project for Cloudron.
- Greenfield: `dsd-cloudron new` scaffolds a Cloudron-ready Django project.
- Batteries-included artifact set: PostgreSQL, Redis, Celery, sendmail, OIDC SSO,
  nginx + gunicorn, rendered through one packaging core.
- On-server build via `cloudron install` / `cloudron update`.
- Retrofit `--wagtail`: configure an existing Wagtail project for Cloudron. Renders
  WAGTAILADMIN_BASE_URL and forces the database search backend in cloudron_settings.py
  (overriding an Elasticsearch/OpenSearch backend Cloudron does not provide) and raises
  the default memory limit. The health check stays `/`, which a stock Wagtail site
  answers; multilingual sites add a `/healthz/` view and pass `--health-check-path`.
  Media and renditions persist on /app/data/media. The plain-Django path is unchanged.

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

- Retrofit `--sso` now ships a `cloudron_adapters.py` (an account adapter that
  closes local self-service signup and a social adapter that keeps OIDC
  first-login provisioning) and points `ACCOUNT_ADAPTER`/`SOCIALACCOUNT_ADAPTER`
  at it on Cloudron, matching what a scaffolded project gets. It installs
  `django-allauth[mfa,socialaccount]` and writes the exact
  `INSTALLED_APPS`/`MIDDLEWARE`/`urls.py` wiring block into `README-cloudron.md`
  and a `CLOUDRON_NEXT_STEPS.md` operator aid; only those app-list and URLconf
  edits remain yours to apply. The plugin still never edits your `settings.py`
  or `urls.py`.
- Harden the generated artifacts: nginx now sets `X-Forwarded-Proto https`
  literally instead of reflecting the inbound header (the one value
  `SECURE_PROXY_SSL_HEADER` trusts); `.dockerignore` excludes common secret files
  (`*.pem`, `*.key`, `local_settings.py`, `.env.*`, service-account JSON, `*.har`)
  so they cannot bake into an image layer; the Cloudron settings pin
  `SECURE_CONTENT_TYPE_NOSNIFF` and `SECURE_REFERRER_POLICY = "same-origin"`.
- The Cloudron settings also enable `SECURE_SSL_REDIRECT` and a conservative
  one-hour `SECURE_HSTS_SECONDS` under the same gate. Because nginx pins the
  forwarded-proto header (above), the redirect is defense in depth and never
  loops the internal health probe; HSTS starts short and leaves preload and
  include-subdomains off.
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
