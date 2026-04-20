FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

# Tools useful for local/LAN development and diagnostics.
# Includes network tooling used by scripts/hum-dev-netns.sh and
# config authoring helpers for websetup virtual phase files.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bridge-utils \
        ca-certificates \
        curl \
        dnsutils \
        ethtool \
        iproute2 \
        iputils-ping \
        iptables \
        jq \
        kmod \
        net-tools \
        tcpdump \
        traceroute \
        yq \
    && rm -rf /var/lib/apt/lists/*

# squashfs / xz tooling for working with snap packages without snapd.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        file \
        fuse3 \
        squashfs-tools \
        squashfuse \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*
