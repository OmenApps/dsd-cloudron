from dsd_cloudron import packaging


def _cfg(**kw):
    base = dict(project_name="blog", app_id="io.omenapps.blog")
    base.update(kw)
    return packaging.CloudronAppConfig(**base)


def test_wagtail_settings_block_present():
    out = packaging.render_cloudron_settings(_cfg(enable_wagtail=True))
    assert 'WAGTAILADMIN_BASE_URL = os.environ["CLOUDRON_APP_ORIGIN"]' in out
    # Pin the backend setting name too, so a typo in WAGTAILSEARCH_BACKENDS
    # cannot pass on the value substring alone.
    assert "WAGTAILSEARCH_BACKENDS = {" in out
    assert '"BACKEND": "wagtail.search.backends.database"' in out
    # Stays under the CLOUDRON_APP_ORIGIN gate: 4-space indented.
    assert "    WAGTAILADMIN_BASE_URL" in out


def test_wagtail_settings_block_absent_by_default():
    out = packaging.render_cloudron_settings(_cfg())
    assert "WAGTAILADMIN_BASE_URL" not in out
    assert "wagtail.search.backends.database" not in out


def test_context_exposes_enable_wagtail():
    assert packaging._context(_cfg(enable_wagtail=True))["enable_wagtail"] is True
    assert packaging._context(_cfg())["enable_wagtail"] is False


def test_readme_has_wagtail_section():
    out = packaging.render_readme(_cfg(enable_wagtail=True))
    assert "Wagtail on Cloudron" in out
    assert "Wagtail on Cloudron" not in packaging.render_readme(_cfg())


def test_wagtail_flag_blast_radius_is_narrow():
    # The --wagtail flag's blast radius is cloudron_settings.py, the manifest, the
    # README, and one purely-additive block in start.sh (the Site-record sync). The
    # Dockerfile and nginx.conf must render byte-identically with and without it, so a
    # future edit that accidentally branched one of them on enable_wagtail fails here.
    import difflib

    plain = _cfg()
    wag = _cfg(enable_wagtail=True)
    assert packaging.render_dockerfile(plain) == packaging.render_dockerfile(wag)
    assert packaging.render_nginx_conf(plain) == packaging.render_nginx_conf(wag)
    # start.sh gains ONLY the Wagtail Site-sync block: the diff against the plain
    # script is purely additive (no line removed or changed), and the added lines
    # include the sync. This keeps the newline-neutral insertion honest.
    plain_sh = packaging.render_start_sh(plain).splitlines()
    wag_sh = packaging.render_start_sh(wag).splitlines()
    diff = list(difflib.ndiff(plain_sh, wag_sh))
    assert not [line for line in diff if line.startswith("- ")]
    added = [line[2:] for line in diff if line.startswith("+ ")]
    assert any("is_default_site=True" in line for line in added)


def test_wagtail_and_celery_coexist():
    # The plan requires --wagtail --celery to work together. At the settings level
    # both blocks must render: the Wagtail glue and the Celery broker. (The container
    # pin that makes the celery worker load the same gated settings module - so it
    # reaches the broker - is exercised by the start.sh render tests.)
    out = packaging.render_cloudron_settings(
        _cfg(enable_wagtail=True, enable_celery=True, enable_redis=True)
    )
    assert 'WAGTAILADMIN_BASE_URL = os.environ["CLOUDRON_APP_ORIGIN"]' in out
    assert 'CELERY_BROKER_URL = os.environ["CLOUDRON_REDIS_URL"]' in out
