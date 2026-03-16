FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

# Tools useful for local/LAN development and diagnostics.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        dnsutils \
        iproute2 \
        iputils-ping \
        net-tools \
        traceroute \
    && rm -rf /var/lib/apt/lists/*
