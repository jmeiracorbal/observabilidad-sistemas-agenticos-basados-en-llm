FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ARG MNEMO_VERSION=v0.15.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && ARCH=$(dpkg --print-architecture) \
    && case "$ARCH" in \
        amd64) MNEMO_ARCH=amd64 ;; \
        arm64) MNEMO_ARCH=arm64 ;; \
        *) echo "arquitectura no soportada: $ARCH" && exit 1 ;; \
    esac \
    && curl -sSfL "https://github.com/jmeiracorbal/mnemo/releases/download/${MNEMO_VERSION}/mnemo-linux-${MNEMO_ARCH}" \
        -o /usr/local/bin/mnemo \
    && chmod +x /usr/local/bin/mnemo \
    && mnemo version

WORKDIR /app

COPY pyproject.toml .
RUN uv pip install --system --no-cache .

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
