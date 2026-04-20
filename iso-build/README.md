# HUM ISO build recipe

This directory contains a reproducible live ISO recipe so your build process
is preserved in git and does not depend on an ephemeral home directory.

## Build prerequisites (Debian/Ubuntu host)

```bash
sudo apt-get update
sudo apt-get install -y live-build xorriso isolinux syslinux grub-efi-amd64-bin
```

## Build

From repository root:

```bash
sudo bash iso-build/build.sh
```

### Mirror overrides (optional)

If your environment blocks the default Debian mirrors, override them at runtime:

```bash
sudo HUM_DEBIAN_MIRROR="http://your-mirror/debian/" \
     HUM_DEBIAN_SECURITY_MIRROR="http://your-mirror/debian-security/" \
     bash iso-build/build.sh
```

Artifacts are copied to:

- `data/iso-output/hum-live-<timestamp>.iso`
- `data/iso-output/hum-live-<timestamp>.iso.sha256`

## Notes

- This recipe is intentionally minimal and stable.
- You can customize package sets in `config/package-lists/`.
- Add extra files under `config/includes.chroot/`.
- Mirrors can be changed per run with `HUM_DEBIAN_MIRROR` and
  `HUM_DEBIAN_SECURITY_MIRROR`.
