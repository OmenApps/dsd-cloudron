from dsd_cloudron.packaging import CloudronAppConfig, render_supervisor_confs


def _confs(**kwargs):
    config = CloudronAppConfig(project_name="blog", app_id="com.example.blog", **kwargs)
    return render_supervisor_confs(config)


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
    g = _confs()["gunicorn.conf"]
    assert "[program:gunicorn]" in g
    assert "user=cloudron" in g
    assert "environment=HOME=/home/cloudron,USER=cloudron" in g
    assert "blog.wsgi:application" in g
    assert "--bind unix:/run/blog/gunicorn.sock" in g
    assert '--forwarded-allow-ips="*"' in g


def test_all_programs_log_to_stdio_with_no_rotation():
    for contents in _confs(enable_celery=True).values():
        assert "stdout_logfile=/dev/stdout" in contents
        assert "stdout_logfile_maxbytes=0" in contents
        assert "stderr_logfile=/dev/stderr" in contents
        assert "stderr_logfile_maxbytes=0" in contents


def test_nginx_program_runs_config_and_has_no_user_line():
    n = _confs()["nginx.conf"]
    assert "nginx -c /app/pkg/nginx.conf" in n
    assert "user=" not in n


def test_celery_worker_command_bounded_concurrency():
    worker = _confs(enable_celery=True)["celery-worker.conf"]
    assert "celery -A blog worker" in worker
    # Bound concurrency so the prefork pool does not default to the host CPU
    # count (cgroup-unaware) and OOM against the memory limit.
    assert "--concurrency=2" in worker


def test_celery_beat_schedule_persists_on_app_data():
    confs = _confs(enable_celery=True)
    beat = confs["celery-beat.conf"]
    assert "celery -A blog beat" in beat
    # The schedule file tracks last-run times and must survive restarts, so it
    # lives on the persistent /app/data volume, not on tmpfs /run.
    assert "--schedule /app/data/celerybeat-schedule" in beat
    assert "/run/" not in beat
