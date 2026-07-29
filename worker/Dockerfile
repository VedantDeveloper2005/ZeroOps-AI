FROM mcr.microsoft.com/azure-cli:2.87.0-azurelinux3.0

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/zeroops/bin:${PATH}"

RUN tdnf update -y \
    && tdnf install -y ca-certificates git python3 python3-pip \
    && tdnf clean all

COPY backend/requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/zeroops \
    && /opt/zeroops/bin/python -m pip install --no-cache-dir --upgrade pip \
    && /opt/zeroops/bin/python -m pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt

RUN useradd --create-home --uid 10001 zeroops \
    && mkdir -p /app/backend/workspace \
    && chown -R zeroops:zeroops /app /opt/zeroops

WORKDIR /app
COPY --chown=zeroops:zeroops backend /app/backend
COPY --chown=zeroops:zeroops worker /app/worker

USER zeroops
EXPOSE 8085

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8085/ready', timeout=3)"

CMD ["python", "-m", "worker.main"]
