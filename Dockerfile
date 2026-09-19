# syntax=docker/dockerfile:1.7
FROM python:3.13.13-slim-bookworm@sha256:f576b530293e74140ea91d262232648d5c4f45640a95ec447757701bfcacf034 AS wheels
WORKDIR /build
COPY requirements.lock ./requirements.lock
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.lock

FROM python:3.13.13-slim-bookworm@sha256:f576b530293e74140ea91d262232648d5c4f45640a95ec447757701bfcacf034
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/home/node-map/.local/bin:$PATH
RUN groupadd --gid 10001 node-map \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin node-map \
    && mkdir -p /app /data/geoip \
    && chown -R node-map:node-map /app /data /home/node-map
COPY --from=wheels /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels /wheels/* \
    && rm -rf /wheels
WORKDIR /app
COPY --chown=node-map:node-map app ./app
COPY --chown=node-map:node-map static ./static
USER 10001:10001
EXPOSE 8080
VOLUME ["/data"]
ENTRYPOINT ["python", "-m", "app.run"]
