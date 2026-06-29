import json
import stat

from dsd_cloudron.packaging import CloudronAppConfig, render_all


def _config(**kwargs):
    return CloudronAppConfig(project_name="blog", app_id="com.example.blog", **kwargs)


def test_render_all_writes_full_artifact_set(tmp_path):
    result = render_all(_config(), tmp_path)

    expected = {
        tmp_path / "CloudronManifest.json",
        tmp_path / "Dockerfile",
        tmp_path / "start.sh",
        tmp_path / "nginx.conf",
        tmp_path / ".dockerignore",
        tmp_path / "README-cloudron.md",
        tmp_path / "blog" / "cloudron_settings.py",
        tmp_path / "supervisor" / "gunicorn.conf",
        tmp_path / "supervisor" / "nginx.conf",
    }
    assert expected <= set(result.written)
    for path in expected:
        assert path.exists()
    assert result.skipped == []


def test_render_all_celery_adds_supervisor_confs(tmp_path):
    render_all(_config(enable_celery=True), tmp_path)
    assert (tmp_path / "supervisor" / "celery-worker.conf").exists()
    assert (tmp_path / "supervisor" / "celery-beat.conf").exists()


def test_render_all_celery_writes_celery_app(tmp_path):
    # The worker/beat confs run `celery -A blog`, so render_all must also write
    # the project package's celery.py; without it the worker cannot import its app.
    render_all(_config(enable_celery=True), tmp_path)
    celery_py = tmp_path / "blog" / "celery.py"
    assert celery_py.exists()
    assert 'Celery("blog")' in celery_py.read_text(encoding="utf-8")


def test_render_all_without_celery_omits_celery_app(tmp_path):
    render_all(_config(enable_celery=False), tmp_path)
    assert not (tmp_path / "blog" / "celery.py").exists()


def test_start_sh_is_executable(tmp_path):
    render_all(_config(), tmp_path)
    mode = (tmp_path / "start.sh").stat().st_mode
    assert mode & stat.S_IXUSR


def test_manifest_on_disk_is_valid_json(tmp_path):
    render_all(_config(), tmp_path)
    json.loads((tmp_path / "CloudronManifest.json").read_text())


def test_skip_if_present_preserves_edits(tmp_path):
    render_all(_config(), tmp_path)
    manifest = tmp_path / "CloudronManifest.json"
    manifest.write_text('{"hand": "edited"}\n')

    result = render_all(_config(), tmp_path)
    assert manifest in result.skipped
    assert manifest.read_text() == '{"hand": "edited"}\n'


def test_mixed_skip_and_write_covers_full_set(tmp_path):
    # A second render where only some files are missing must write the missing
    # ones and skip the rest, with written + skipped covering the full set (the
    # skip path must not short-circuit the rest of the orchestration).
    first = render_all(_config(), tmp_path)
    full_set = set(first.written)

    (tmp_path / "Dockerfile").unlink()
    (tmp_path / "supervisor" / "gunicorn.conf").unlink()

    second = render_all(_config(), tmp_path)
    assert tmp_path / "Dockerfile" in second.written
    assert tmp_path / "supervisor" / "gunicorn.conf" in second.written
    assert set(second.written) | set(second.skipped) == full_set
    assert set(second.written) & set(second.skipped) == set()


def test_force_overwrites(tmp_path):
    render_all(_config(), tmp_path)
    manifest = tmp_path / "CloudronManifest.json"
    manifest.write_text('{"hand": "edited"}\n')

    result = render_all(_config(), tmp_path, force=True)
    assert manifest in result.written
    assert json.loads(manifest.read_text())["manifestVersion"] == 2
