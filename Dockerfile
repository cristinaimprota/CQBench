FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
ARG PMD_VERSION=7.11.0

RUN apt-get update && apt-get install -y --no-install-recommends \
    clang-tidy-18 \
    curl \
    openjdk-21-jre-headless \
    python3 \
    python3-pip \
    unzip \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL \
    "https://github.com/pmd/pmd/releases/download/pmd_releases%2F${PMD_VERSION}/pmd-dist-${PMD_VERSION}-bin.zip" \
    -o /tmp/pmd.zip \
    && unzip -q /tmp/pmd.zip -d /opt \
    && ln -s "/opt/pmd-bin-${PMD_VERSION}/bin/pmd" /usr/local/bin/pmd \
    && ln -s /usr/bin/clang-tidy-18 /usr/local/bin/clang-tidy \
    && rm /tmp/pmd.zip

WORKDIR /workspace
COPY . /workspace

RUN python3 -m pip install --break-system-packages --no-cache-dir ".[analysis,test]"

ENV PYTHONPATH=/workspace
ENV HOME=/tmp
ENV SEMGREP_SETTINGS_FILE=/tmp/cqbench-semgrep-settings.yml
ENTRYPOINT ["python3", "-m", "cqbench"]
