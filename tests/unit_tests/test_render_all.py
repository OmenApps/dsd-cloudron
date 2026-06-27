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


def test_force_overwrites(tmp_path):
    render_all(_config(), tmp_path)
    manifest = tmp_path / "CloudronManifest.json"
    manifest.write_text('{"hand": "edited"}\n')

    result = render_all(_config(), tmp_path, force=True)
    assert manifest in result.written
    assert json.loads(manifest.read_text())["manifestVersion"] == 2
