import configparser

from dsd_cloudron.packaging import CloudronAppConfig, render_supervisor_confs


def _confs(**kwargs):
    config = CloudronAppConfig(project_name="blog", app_id="com.example.blog", **kwargs)
    return render_supervisor_confs(config)


def _parse(conf):
    # Parse the rendered conf as the real INI it is, so key/value assertions are
    # exact instead of substring ("user=cloudron" in text also matches
    # "user=cloudronx"). interpolation=None: supervisor command=/environment=
    # values can legitimately carry a literal % (e.g. a gunicorn access-log
    # format), which the default BasicInterpolation would raise on. The current
    # confs have none, but the parser must not become the thing that breaks.
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_string(conf)
    return cfg


def test_default_programs_present():
    confs = _confs()
    assert set(confs) == {"gunicorn.conf", "nginx.conf"}


def test_celery_programs_added_when_enabled():
    confs = _confs(enable_celery=True)
    assert set(confs) == {
        "gunicorn.conf",
        "nginx.conf",
        "celery-worker.conf",
        "celery-beat.conf",
    }


def test_gunicorn_binds_unix_socket_as_cloudron():
    program = _parse(_confs()["gunicorn.conf"])["program:gunicorn"]
    # Exact key/value pairs, so a stray "user=cloudronx" or a mangled environment
    # line cannot pass the way a substring check would.
    assert program["user"] == "cloudron"
    # HOME must point at a writable dir; /home/cloudron is read-only on Cloudron,
    # so gunicorn's ~/.gunicorn write fails there. /tmp is writable and ephemeral.
    assert program["environment"] == "HOME=/tmp,USER=cloudron"
    command = program["command"]
    assert "blog.wsgi:application" in command
    assert "--bind unix:/run/blog/gunicorn.sock" in command
    assert '--forwarded-allow-ips="*"' in command
    assert "/home/cloudron" not in command


def test_all_programs_log_to_stdio_with_no_rotation():
    for contents in _confs(enable_celery=True).values():
        cfg = _parse(contents)
        program = cfg[cfg.sections()[0]]  # each conf declares exactly one program
        assert program["stdout_logfile"] == "/dev/stdout"
        assert program["stdout_logfile_maxbytes"] == "0"
        assert program["stderr_logfile"] == "/dev/stderr"
        assert program["stderr_logfile_maxbytes"] == "0"


def test_nginx_program_runs_config_and_has_no_user_line():
    program = _parse(_confs()["nginx.conf"])["program:nginx"]
    assert "nginx -c /app/pkg/nginx.conf" in program["command"]
    # nginx must carry no user= key of its own (it manages its own worker user);
    # an exact key check avoids the false hit a bare "user=" substring would take
    # on the other programs' "environment=...USER=cloudron".
    assert "user" not in program


def test_celery_worker_command_bounded_concurrency():
    command = _parse(_confs(enable_celery=True)["celery-worker.conf"])[
        "program:celery-worker"
    ]["command"]
    assert "celery -A blog worker" in command
    # Bound concurrency so the prefork pool does not default to the host CPU
    # count (cgroup-unaware) and OOM against the memory limit.
    assert "--concurrency=2" in command


def test_celery_beat_schedule_persists_on_app_data():
    command = _parse(_confs(enable_celery=True)["celery-beat.conf"])[
        "program:celery-beat"
    ]["command"]
    assert "celery -A blog beat" in command
    # The schedule file tracks last-run times and must survive restarts, so it
    # lives on the persistent /app/data volume, not on tmpfs /run.
    assert "--schedule /app/data/celerybeat-schedule" in command
    assert "/run/" not in command
