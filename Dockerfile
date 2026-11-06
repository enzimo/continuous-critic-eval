FROM python:3.13-slim AS build
WORKDIR /build
COPY requirements.lock pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir --prefix=/install -r requirements.lock \
    && pip install --no-cache-dir --no-deps --prefix=/install .

FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    OBSERVER_DATABASE=/data/observer.sqlite3
RUN groupadd --gid 10001 observer \
    && useradd --uid 10001 --gid 10001 --no-create-home observer \
    && mkdir /data && chown 10001:10001 /data
COPY --from=build /install /usr/local
USER 10001:10001
WORKDIR /data
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()"]
ENTRYPOINT ["critic-observer"]
CMD ["serve"]
