# Changelog

## 0.1.0 - unreleased

Initial release.

- Retrofit: `manage.py deploy` configures an existing Django project for Cloudron.
- Greenfield: `dsd-cloudron new` scaffolds a Cloudron-ready Django project.
- Batteries-included artifact set: PostgreSQL, Redis, Celery, sendmail, OIDC SSO,
  nginx + gunicorn, rendered through one packaging core.
- On-server build via `cloudron install` / `cloudron update`.
