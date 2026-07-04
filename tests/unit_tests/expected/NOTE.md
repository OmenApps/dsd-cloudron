# Golden fixtures

`test_golden_snapshot.py` diffs each `render_*(config)` output byte-for-byte
against the files here, catching formatting or ordering drift the substring tests
miss. They are all produced for the sample project package name `blog`.

- `CloudronManifest.json`, `Dockerfile`, `start.sh`, `nginx.conf`,
  `cloudron_settings.py`, `celery.py` - the default `blog` config
  (`CloudronAppConfig(project_name="blog", app_id="com.example.blog")`).
- `uv.Dockerfile` - `render_dockerfile` with `pkg_manager="uv"` (the greenfield
  scaffolder's package manager, which installs from `pyproject.toml`).

The celery+sso goldens live under
`tests/integration_tests/reference_files/celery_sso.*` and are read from there
(one source of truth shared with the integration suite), not copied here.

## Regenerating

If a render function's output legitimately changes, regenerate the affected file
and confirm the diff by eye before committing. For example:

```bash
python - <<'PY'
from pathlib import Path
from dsd_cloudron.packaging import CloudronAppConfig, render_dockerfile
config = CloudronAppConfig(project_name="blog", app_id="com.example.blog", pkg_manager="uv")
Path("tests/unit_tests/expected/uv.Dockerfile").write_text(render_dockerfile(config), encoding="utf-8")
PY
```

This directory is force-excluded from `black` (see `pyproject.toml`), so the
goldens are never reformatted out from under the byte-exact comparison.
