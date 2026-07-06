# Contributing

A short appendix for working on dsd-cloudron itself, not on a project that
uses it.

## Install

```bash
pip install -e ".[dev]"
```

This pulls in `black`, `ruff`, `build`, `pytest`, `pytest-cookies`,
`coverage`, and `twine`. To also run the toggle-on bake tests, install the
`bake` extra alongside it:

```bash
pip install -e ".[dev,bake]"
```

The bake tests shell out to a generated project with the outer Python
interpreter, so the packages a baked project might depend on (Celery,
django-allauth, django-ninja, and so on) need to be importable in *your* test
environment too - listing them in the baked project's own `pyproject.toml`
isn't enough. Each bake test still `importorskip`s the package it needs, so a
`dev`-only environment skips them instead of failing.

## Test layout

Always run pytest as a module, from the repository root:

```bash
python -m pytest
```

A bare `pytest` can pick up a different interpreter and a different config
file; a module run uses this interpreter, and `testpaths` keeps collection
inside `tests/`. The run prints a `dsd-cloudron test tiers:` line naming any
tier that was skipped, so a green run never hides one.

`python -m pytest` runs the offline suites - `tests/unit_tests`,
`tests/integration_tests`, `tests/bake_tests`, and `tests/build_tests`. The
integration tests depend on django-simple-deploy's own test harness; when
that harness isn't importable, `tests/conftest.py` skips collecting them
rather than erroring, so a bare run still passes in a minimal checkout. The
bake tests in `tests/bake_tests` are skipped the same way when
`pytest-cookies` (the `dev` extra) isn't installed.

`tests/e2e_tests` performs a real deployment against a live Cloudron server
and is excluded from collection entirely (`collect_ignore` in
`tests/conftest.py`). Run it deliberately, with `cloudron login` done and the
target subdomain in `CLOUDRON_E2E_LOCATION`, not as part of routine
development:

```bash
CLOUDRON_E2E_LOCATION=dsd-e2e python -m pytest tests/e2e_tests
```

To run a single file or test:

```bash
python -m pytest tests/unit_tests/test_render_start_sh.py
python -m pytest tests/unit_tests/test_render_start_sh.py::test_chown_and_exec_supervisord
```

## Formatting

```bash
black .
```

`pyproject.toml` excludes the golden snapshot fixtures
(`tests/unit_tests/expected/`), the integration reference files
(`tests/integration_tests/reference_files/`), and the project scaffold
template (`dsd_cloudron/project_template/`) from formatting. Those are
byte-exact render output, not source to clean up - running `black` over them
would make them stop matching what the render functions actually produce.

## Build and release

```bash
python -m build
twine upload dist/*
```

See {doc}`/reference/cli` for the CLI surface and
{doc}`/reference/generated-files` for what the package renders into a
deployed project.
