# HUM circuits (blogspot delivery)

Simple pages for the ongoing virtio housing: guest `/dev/vda` on host `/dev/sda`, a growing ISO list, isolation-zone arithmetic, and one SQL login.

## Policy

- VNC stays on `127.0.0.1` display zones `100+`.
- `/dev/nbd0` stays in zone `300` with `vnc_attach: denied`.
- This tree does not attach VNC to NBD and does not ship Windows or macOS ISOs.

## Commands

```bash
python3 scripts/hum-isolation-zones.py plan
python3 scripts/hum-isolation-zones.py write
python3 scripts/hum-isolation-zones.py virtio
python3 scripts/hum-isolation-zones.py nbd-risk
python3 scripts/hum-ip-drift.py status
python3 scripts/hum-ip-drift.py plan
```
