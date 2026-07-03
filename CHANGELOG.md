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
