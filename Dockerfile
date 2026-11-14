# MastHead for Horizon, server mode. See README "Run it on a server".
#
#   docker compose up -d                                   the console behind Caddy (HTTPS)
#   docker build --target test -t masthead:test . && docker run --rm masthead:test
#                                                          the whole test suite on Linux
#
# Building behind an antivirus or a company proxy that inspects HTTPS: give its
# root certificate as a build secret. It is used for the downloads of this build
# only and is never stored in an image:
#   docker build --secret id=extra_ca,src=proxy-root.pem ...

FROM python:3.12-slim AS build
# git fetches Horizon, which is pinned to one commit in pyproject.toml.
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY pyproject.toml README.md ./
COPY masthead ./masthead
# Two environments: /opt/app for the image that runs, /opt/test with the dev tools.
RUN --mount=type=secret,id=extra_ca,required=false \
    set -e; \
    if [ -s /run/secrets/extra_ca ]; then \
      cat /etc/ssl/certs/ca-certificates.crt /run/secrets/extra_ca > /tmp/ca.pem; \
      export SSL_CERT_FILE=/tmp/ca.pem PIP_CERT=/tmp/ca.pem GIT_SSL_CAINFO=/tmp/ca.pem; \
    fi; \
    pip install --no-cache-dir "uv>=0.5,<1"; \
    export UV_NO_CACHE=1 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1; \
    uv venv --quiet /opt/app && uv pip install --quiet --python /opt/app/bin/python .; \
    uv venv --quiet /opt/test && uv pip install --quiet --python /opt/test/bin/python ".[dev]"; \
    rm -f /tmp/ca.pem

FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MASTHEAD_HOME=/data PATH=/opt/app/bin:$PATH
COPY --from=build /opt/app /opt/app
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin masthead \
    && mkdir -p /data && chown masthead:masthead /data
USER masthead
VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=4).status == 200 else 1)"]
CMD ["masthead", "serve", "--server", "--host", "0.0.0.0", "--port", "8765", "--no-browser"]

# The whole test suite on Linux, as root so that one test can add a root
# certificate to the system store (the certificate store fix), then remove it.
FROM python:3.12-slim AS test
ENV PYTHONDONTWRITEBYTECODE=1 PATH=/opt/test/bin:$PATH MASTHEAD_SYSTEM_CA_TEST=1
COPY --from=build /opt/test /opt/test
WORKDIR /src
COPY pyproject.toml ./
COPY tests ./tests
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
