FROM cloudron/base:5.0.0@sha256:04fd70dbd8ad6149c19de39e35718e024417c3e01dc9c6637eaf4a41ec4e596c

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV VENV_PATH=/app/code/venv
ENV PATH=$VENV_PATH/bin:$PATH

RUN mkdir -p /app/code /app/pkg
WORKDIR /app/code

RUN python3 -m venv $VENV_PATH

# No apt step for Postgres: the pinned cloudron/base already ships libpq
# (libpq.so.5 plus pg_config/headers) and a compiler, so psycopg installs and
# runs whether the project pins psycopg[binary] or a non-binary psycopg. A base
# bump that dropped these would break non-binary psycopg - the CI base-digest
# drift check is the signal to re-verify.
COPY requirements.txt /app/code/requirements.txt
RUN $VENV_PATH/bin/pip install --no-cache-dir --upgrade pip uv && \
    uv pip install --python $VENV_PATH/bin/python -r /app/code/requirements.txt

COPY . /app/code/

# Relocate the supervisord master log off the read-only image layer.
RUN sed -e 's,^logfile=.*$,logfile=/run/supervisord.log,' -i /etc/supervisor/supervisord.conf

# nginx's compiled-in log directory is read-only at runtime; point it at the
# writable /run (matches the tandoor/weblate/pretix Cloudron packages). nginx
# logs to /dev/stdout anyway, but this silences the startup open-log alert.
RUN rm -rf /var/log/nginx && ln -s /run/nginx /var/log/nginx

COPY supervisor/ /etc/supervisor/conf.d/
COPY nginx.conf /app/pkg/nginx.conf
COPY start.sh /app/pkg/start.sh
RUN chmod +x /app/pkg/start.sh

# Static files are gathered at container start, not during the image build,
# because the build has no CLOUDRON_* env, no SECRET_KEY, and no writable target.
# start.sh gathers them into /run, where STATIC_ROOT points directly.

CMD ["/app/pkg/start.sh"]
