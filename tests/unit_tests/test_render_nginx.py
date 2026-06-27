from dsd_cloudron.packaging import CloudronAppConfig, render_nginx_conf


def _nginx(**kwargs):
    config = CloudronAppConfig(project_name="blog", app_id="com.example.blog", **kwargs)
    return render_nginx_conf(config)


def test_listens_on_http_port():
    assert "listen 8000;" in _nginx()
    assert "listen 9000;" in _nginx(http_port=9000)


def test_forwarded_proto_is_passthrough_not_scheme():
    text = _nginx()
    assert "proxy_set_header X-Forwarded-Proto $http_x_forwarded_proto;" in text
    assert "$scheme" not in text


def test_static_and_media_locations():
    text = _nginx()
    assert "location /static/" in text
    assert "alias /run/blog/static/;" in text
    assert "location /media/" in text
    assert "alias /app/data/media/;" in text


def test_proxies_to_unix_socket():
    assert "proxy_pass http://unix:/run/blog/gunicorn.sock;" in _nginx()


def test_temp_and_pid_paths_under_run():
    text = _nginx()
    assert "pid /run/nginx/nginx.pid;" in text
    assert "proxy_temp_path /run/nginx/proxy_temp;" in text


def test_logs_to_stdout_and_workers_run_as_cloudron():
    text = _nginx()
    assert "access_log /dev/stdout;" in text
    assert "user cloudron;" in text
