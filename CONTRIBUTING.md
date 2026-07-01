# Contributing to dsd-cloudron

dsd-cloudron is a [django-simple-deploy](https://django-simple-deploy.readthedocs.io)
plugin that configures and deploys Django projects to [Cloudron](https://cloudron.io).
This guide covers the local setup and the test tiers so a new run of the suite means
what you think it means.

## Working style

- All work happens on `main`. There are no feature branches or worktrees.
- Run `black .` before every commit. The formatting targets are pinned in
  `pyproject.toml`; continuous integration runs `black --check .` and will fail on
  unformatted code.
- Keep commit messages to a plain sentence of five to twelve words describing the
  change. No conventional-commit prefixes, no co-author or signoff lines.

## Install

Create a virtual environment, then install the plugin with the extras you need:

```bash
pip install -e ".[dev]"        # unit tests, black, build, twine, pytest-cookies
pip install -e ".[dev,bake]"   # the above, plus the runtime packages the bake
                               # toggle tests import (celery, allauth, and so on)
```

Install `.[dev,bake]`, not `.[dev]`, whenever you touch the greenfield scaffolder.
The toggle-on bake tests `importorskip` `celery`/`allauth`/others, so a `.[dev]`-only
environment silently skips the riskiest scaffolds instead of running them.

## Running the tests

Always run pytest as a module from the repository root:

```bash
python -m pytest
```

Running the bare `pytest` entry point can pick up a different interpreter, and
running from elsewhere changes which config file pytest loads. `testpaths` is scoped
to `tests/` so a repo-root run does not wander into the vendored `example-*` trees.

The suite prints a `dsd-cloudron test tiers:` line reporting which tiers did not run,
so a green run never silently hides a skipped tier.

### The four test tiers

- `unit_tests` - fast and fully offline. They exercise the render functions, the
  deployer logic, and the config surface without touching the network or a real
  Cloudron. These always run.
- `integration_tests` - compare generated files against `reference_files/`. They rely
  on the django-simple-deploy core test harness (its `conftest.py`, fixtures, and
  `utils/`), which ships with a source checkout of django-simple-deploy rather than
  the published wheel. When the harness is not importable, this tier is collect-ignored
  and reported as skipped.
- `bake_tests` - bake the greenfield project template with cookiecutter and assert on
  the scaffolded artifacts. They need the `pytest-cookies` plugin (in the `dev` extra)
  and, for the toggle-on scaffolds, the `bake` extra. Without `pytest-cookies` the tier
  is collect-ignored.
- `e2e_tests` - perform a real live deployment against a Cloudron server. They are
  collect-ignored by default. Run them deliberately, with `cloudron login` already
  done and a subdomain to deploy to:

  ```bash
  CLOUDRON_E2E_LOCATION=dsd-e2e python -m pytest tests/e2e_tests/test_deployment.py -p no:cacheprovider
  ```

## Before you open a pull request

- `black --check .` reports no changes.
- `python -m pytest` passes, and the tier line shows the tiers you expected to run.
- If you changed generated output, re-pin the affected golden fixtures in
  `tests/unit_tests/expected/` and the integration `reference_files/`, and confirm the
  new contents by eye before committing.
