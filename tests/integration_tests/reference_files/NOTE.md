# Reference files

The integration tests diff the artifacts a real deploy generates against the
files here. They run only where django-simple-deploy's integration-test harness
is importable (it supplies the `tmp_project`/`pkg_manager`/`dsd_version` fixtures
and the `it_helper_functions`/`manage_sample_project` helpers); the installed
core package does not ship that harness, so the suite is run in CI or a dev
checkout that has it.

## Deterministic references (generated from `packaging.render_all`)

These are byte-identical to what `PlatformDeployer` writes, because both go
through the same render core. They were produced for the sample project package
name `blog`:

- `CloudronManifest.json`, `Dockerfile`, `poetry.Dockerfile`, `pipenv.Dockerfile`
- `start.sh`, `nginx.conf`, `supervisor/gunicorn.conf`
- `blog/cloudron_settings.py`
- `celery_sso.*` (the `--celery --sso` build: manifest, settings, celery worker/beat
  confs, `celery.py`, and the `__init__` wiring)

If the render core changes, regenerate them.

## Harness-derived references (capture from a real harness run)

These depend on the sample project's own baseline, which only exists inside the
harness, so they are intentionally absent here and must be captured the first
time the suite runs (per the plan's bootstrap step):

- `blog/settings.py` - the sample `settings.py` with the appended
  `# dsd-cloudron settings.` block and `from blog.cloudron_settings import *`.
- `requirements.txt` - the sample requirements with `gunicorn`, `psycopg[binary]`,
  `django-redis` added (and the `django-simple-deploy=={current-version}`
  substitution so the `context` interpolation in `test_requirements_txt` matches).

Run `pytest tests/integration_tests/` once, copy the generated files from the
reported `tmp_project` into this directory, review them, then re-run.
