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
        netcat-openbsd \
        python3 \
        python3-pip \
        python3-venv \
        shellcheck \
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

# TestDisk / PhotoRec for recup data recovery and file carving.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        testdisk \
        file \
    && rm -rf /var/lib/apt/lists/*

# Set container origin hostname to HUM.org.
RUN echo "hum.org" > /etc/hostname

# Prepare /home/troy with recup workspace directories.
RUN mkdir -p /home/troy/TEMPLATES /home/troy/PHOTOS /home/troy/recup_output \
    && chmod -R 755 /home/troy

# Copy recup import/organize script into the image.
COPY recup-setup.sh /usr/local/bin/recup-setup
RUN chmod +x /usr/local/bin/recup-setup

# Copy net-driver-recover-auto.sh into the image.
COPY net-driver-recover-auto.sh /usr/local/bin/net-driver-recover-auto.sh
RUN chmod +x /usr/local/bin/net-driver-recover-auto.sh \
    && mkdir -p /var/local/net-driver-recover-backups
