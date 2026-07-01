# Reference files

The integration tests diff the artifacts a real deploy generates against the
files here. They run only where django-simple-deploy's integration-test harness
is importable (it supplies the `tmp_project`/`pkg_manager`/`dsd_version` fixtures
and the `it_helper_functions`/`manage_sample_project` helpers); the installed
core package does not ship that harness, so the suite is run in CI or a dev
checkout that has it.

## Deterministic references (generated from `packaging.render_all`)

These are byte-identical to what `PlatformDeployer` writes, because both go
through the same render core (`packaging.render_all`). They were produced for the
sample project package name `blog`:

- `CloudronManifest.json`, `Dockerfile`, `poetry.Dockerfile`, `pipenv.Dockerfile`
- `start.sh`, `nginx.conf`, `supervisor/gunicorn.conf`, `README-cloudron.md`
- `blog/cloudron_settings.py`
- `celery_sso.*` for the `--celery --sso` build: `celery_sso.CloudronManifest.json`,
  `celery_sso.cloudron_settings.py`, `celery_sso.supervisor.celery-worker.conf`,
  `celery_sso.supervisor.celery-beat.conf`, `celery_sso.celery.py`

If the render core changes, regenerate them.

## Deployer-written reference (not from render_all)

- `celery_sso.init.py` is written by the deployer's `_add_celery_app`, not by
  `render_all`. It assumes a standard `startproject` baseline `__init__.py`
  (empty), so it is exactly the appended import line. If the harness sample's
  `__init__.py` is not empty, recapture this from a harness run.

## Harness-derived references (capture from a real harness run)

These depend on the sample project's own baseline, which only exists inside the
harness, so they are intentionally absent here and must be captured the first
time the suite runs (per the plan's bootstrap step):

- `blog/settings.py` - the sample `settings.py` with the appended
  `# dsd-cloudron settings.` block and `from blog.cloudron_settings import *`.
- `requirements.txt` - the sample requirements with `gunicorn>=22.0`,
  `psycopg[binary]>=3.1`, `django-redis>=5.4` added (each carrying its tested
  version floor) and the `django-simple-deploy=={current-version}` substitution so
  the `context` interpolation in `test_requirements_txt` matches.

Run `pytest tests/integration_tests/` once, copy the generated files from the
reported `tmp_project` into this directory, review them, then re-run.
