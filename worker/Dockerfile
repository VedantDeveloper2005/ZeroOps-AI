FROM --platform=linux/amd64 mcr.microsoft.com/azure-cli:2.87.0-azurelinux3.0@sha256:ae2b53ff3933260ebfd0b1fd0e58650ceb6233bdc7a8f20cef1bea9ebb72dc7e

ARG TERRAFORM_VERSION=1.15.8
ARG TERRAFORM_SHA256=d25ce7b6902013ad905db3d2eab0be4cd905887fe88b81a6171b8d5503c31f3d
ARG TFLINT_VERSION=0.64.0
ARG TFLINT_SHA256=cca9d13e2e1d7a2c627af60ff899a3c9b74212899416aeb96ec764d2ef954537

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH="/opt/zeroops/bin:/usr/local/bin:${PATH}" \
    TF_IN_AUTOMATION=true \
    CHECKPOINT_DISABLE=1

RUN tdnf update -y \
    && tdnf install -y ca-certificates curl git python3 python3-pip shadow-utils unzip \
    && tdnf clean all

RUN curl --fail --show-error --silent --location \
      "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip" \
      --output /tmp/terraform.zip \
    && echo "${TERRAFORM_SHA256}  /tmp/terraform.zip" | sha256sum --check --strict \
    && unzip -q /tmp/terraform.zip -d /usr/local/bin \
    && rm -f /tmp/terraform.zip \
    && terraform version

RUN curl --fail --show-error --silent --location \
      "https://github.com/terraform-linters/tflint/releases/download/v${TFLINT_VERSION}/tflint_linux_amd64.zip" \
      --output /tmp/tflint.zip \
    && echo "${TFLINT_SHA256}  /tmp/tflint.zip" | sha256sum --check --strict \
    && unzip -q /tmp/tflint.zip -d /usr/local/bin \
    && rm -f /tmp/tflint.zip \
    && tflint --version

COPY worker/requirements.vmss.txt /tmp/requirements.vmss.txt
RUN python3 -m venv /opt/zeroops \
    && /opt/zeroops/bin/python -m pip install --no-cache-dir --upgrade pip \
    && /opt/zeroops/bin/python -m pip install --no-cache-dir -r /tmp/requirements.vmss.txt \
    && rm -f /tmp/requirements.vmss.txt \
    && checkov --version

RUN useradd --create-home --uid 10001 --shell /sbin/nologin zeroops \
    && install -d -o root -g root -m 0755 /app \
    && install -d -o zeroops -g zeroops -m 0700 /work

WORKDIR /app
COPY --chown=root:root worker /app/worker
RUN chmod -R a-w /app

USER zeroops
EXPOSE 8085

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8085/ready', timeout=3)"

CMD ["python", "-m", "worker.vmss_main"]
