import json

import pytest

from dsd_cloudron.packaging import (
    CloudronAppConfig,
    ReconfigureError,
    apply_manifest_values,
    reconfigure,
    render_all,
)


def _config(**kwargs):
    return CloudronAppConfig(project_name="blog", app_id="com.example.blog", **kwargs)


class _Recorder:
    """A stand-in for the injected confirm/output callbacks.

    `events` is a single ordered log of both callbacks so a test can assert that a
    diff was emitted (output) before its file was prompted (confirm); `prompted` and
    `lines` are the flat views the other tests read.
    """

    def __init__(self, answer=True):
        self.answer = answer
        self.prompted = []
        self.lines = []
        self.events = []

    def confirm(self, path):
        self.prompted.append(path)
        self.events.append(("confirm", path))
        return self.answer

    def output(self, message):
        self.lines.append(message)
        self.events.append(("output", message))


def test_reconfigure_requires_a_manifest(tmp_path):
    # Reconfigure re-renders an already-deployed project; with no manifest there is
    # no deployed state to preserve, so it aborts rather than half-writing one.
    rec = _Recorder()
    with pytest.raises(ReconfigureError):
        reconfigure(_config(), tmp_path, confirm=rec.confirm, output=rec.output)


@pytest.mark.parametrize(
    "flag", ["enable_redis", "enable_sendmail", "enable_sso", "enable_celery"]
)
def test_reconfigure_refuses_a_stack_toggle(tmp_path, flag):
    # render_all leaves redis+sendmail on and sso+celery off; flipping ANY one of the
    # four stack flags needs deps + wiring reconfigure does not touch (each flag has its
    # own hand-written on-disk probe), so it must refuse before writing or prompting for
    # anything rather than shipping a broken image.
    render_all(_config(), tmp_path)
    rec = _Recorder(answer=True)
    flipped = not getattr(_config(), flag)
    with pytest.raises(ReconfigureError):
        reconfigure(
            _config(**{flag: flipped}),
            tmp_path,
            confirm=rec.confirm,
            output=rec.output,
        )
    assert rec.prompted == []
    assert not (tmp_path / "blog" / "celery.py").exists()


def test_reconfigure_rejects_a_corrupt_manifest(tmp_path):
    render_all(_config(), tmp_path)
    (tmp_path / "CloudronManifest.json").write_text("{ not json", encoding="utf-8")
    rec = _Recorder()
    with pytest.raises(ReconfigureError):
        reconfigure(_config(), tmp_path, confirm=rec.confirm, output=rec.output)
    assert rec.prompted == []


def test_reconfigure_rejects_a_non_utf8_manifest(tmp_path):
    # A manifest saved in a non-UTF-8 encoding raises UnicodeDecodeError (a ValueError,
    # not JSONDecodeError) before json parses it; it must still abort cleanly as a
    # ReconfigureError before any prompt or write, not leak a raw traceback.
    render_all(_config(), tmp_path)
    (tmp_path / "CloudronManifest.json").write_bytes(b"\xff\xfe not utf-8")
    rec = _Recorder()
    with pytest.raises(ReconfigureError):
        reconfigure(_config(), tmp_path, confirm=rec.confirm, output=rec.output)
    assert rec.prompted == []


def test_reconfigure_rejects_a_non_utf8_artifact(tmp_path):
    # A hand-edited artifact saved in a non-UTF-8 encoding cannot be diffed; reconfigure
    # aborts as a ReconfigureError (which both callers translate) rather than raising a
    # raw UnicodeDecodeError the retrofit caller's OSError handler would miss.
    render_all(_config(), tmp_path)
    (tmp_path / "Dockerfile").write_bytes(b"FROM python\n\xff\xfe\n")
    rec = _Recorder()
    with pytest.raises(ReconfigureError):
        reconfigure(_config(), tmp_path, confirm=rec.confirm, output=rec.output)


def test_unchanged_artifacts_are_not_prompted_or_written(tmp_path):
    render_all(_config(), tmp_path)
    rec = _Recorder()
    result = reconfigure(_config(), tmp_path, confirm=rec.confirm, output=rec.output)
    assert rec.prompted == []
    assert result.overwritten == []
    assert (tmp_path / "Dockerfile") in result.unchanged


def test_changed_artifact_prompts_and_overwrites_on_yes(tmp_path):
    render_all(_config(), tmp_path)
    dockerfile = tmp_path / "Dockerfile"
    fresh = dockerfile.read_text(encoding="utf-8")
    dockerfile.write_text("HAND EDIT\n", encoding="utf-8")
    rec = _Recorder(answer=True)
    result = reconfigure(_config(), tmp_path, confirm=rec.confirm, output=rec.output)
    assert dockerfile in rec.prompted
    assert dockerfile in result.overwritten
    assert dockerfile.read_text(encoding="utf-8") == fresh


def test_changed_artifact_left_untouched_on_no(tmp_path):
    render_all(_config(), tmp_path)
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("HAND EDIT\n", encoding="utf-8")
    rec = _Recorder(answer=False)
    result = reconfigure(_config(), tmp_path, confirm=rec.confirm, output=rec.output)
    assert dockerfile in rec.prompted
    assert dockerfile in result.declined
    assert dockerfile.read_text(encoding="utf-8") == "HAND EDIT\n"


def test_diff_is_emitted_before_confirm(tmp_path):
    render_all(_config(), tmp_path)
    (tmp_path / "Dockerfile").write_text("HAND EDIT\n", encoding="utf-8")
    rec = _Recorder(answer=False)
    reconfigure(_config(), tmp_path, confirm=rec.confirm, output=rec.output)
    # The diff must be emitted via output() BEFORE the file's confirm() is asked, so the
    # operator decides on a change they have already seen. Assert on the ordered event
    # log, not two separate lists, so a regression that swapped the order would fail.
    first_confirm = next(
        i for i, (kind, _) in enumerate(rec.events) if kind == "confirm"
    )
    emitted_before_prompt = "".join(
        message for kind, message in rec.events[:first_confirm] if kind == "output"
    )
    assert "HAND EDIT" in emitted_before_prompt
    assert "--- " in emitted_before_prompt


def test_manifest_scalar_is_synced_not_diffed(tmp_path):
    render_all(_config(), tmp_path)
    manifest = tmp_path / "CloudronManifest.json"
    rec = _Recorder(answer=True)
    # memory_limit is the same stack set (only a scalar changes), so the guard passes
    # and the value is synced surgically - never shown in the confirm loop.
    result = reconfigure(
        _config(memory_limit=2147483648),
        tmp_path,
        confirm=rec.confirm,
        output=rec.output,
    )
    assert manifest not in rec.prompted
    assert result.manifest_changed is True
    assert json.loads(manifest.read_text())["memoryLimit"] == 2147483648


def test_apply_manifest_values_preserves_everything_but_the_two_scalars(tmp_path):
    render_all(_config(), tmp_path)
    manifest_path = tmp_path / "CloudronManifest.json"
    data = json.loads(manifest_path.read_text())
    data["customKey"] = "keep me"
    data["addons"]["mongodb"] = {}
    original_title = data["title"]
    manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    changed = apply_manifest_values(_config(memory_limit=2147483648), manifest_path)
    assert changed is True
    result = json.loads(manifest_path.read_text())
    assert result["memoryLimit"] == 2147483648
    assert result["customKey"] == "keep me"
    assert result["addons"]["mongodb"] == {}
    assert result["title"] == original_title


def test_apply_manifest_values_leaves_addons_untouched(tmp_path):
    render_all(_config(), tmp_path)  # redis + sendmail on, no oidc
    manifest_path = tmp_path / "CloudronManifest.json"
    before = json.loads(manifest_path.read_text())["addons"]
    # apply_manifest_values never toggles addons, even when the config disagrees; the
    # reconfigure stack guard is what keeps the addon set and the config consistent.
    apply_manifest_values(_config(enable_redis=False, enable_sso=True), manifest_path)
    after = json.loads(manifest_path.read_text())["addons"]
    assert after == before


def test_apply_manifest_values_noop_returns_false(tmp_path):
    render_all(_config(), tmp_path)
    manifest_path = tmp_path / "CloudronManifest.json"
    assert apply_manifest_values(_config(), manifest_path) is False
