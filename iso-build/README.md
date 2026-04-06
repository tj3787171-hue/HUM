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
bash iso-build/build.sh
```

Artifacts are copied to:

- `data/iso-output/hum-live-amd64.iso`
- `data/iso-output/hum-live-amd64.iso.sha256`

## Notes

- This recipe is intentionally minimal and stable.
- You can customize package sets in `config/package-lists/`.
- Add extra files under `config/includes.chroot/`.
