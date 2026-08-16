# HUM HTTPS broadcast (LVM-cache frontend)

Self-hosted Python TLS desk. Builds searchable hypertext from login + circuits, then serves the cache. The public cert is broadcast. The private key is not.

## Desktop agent

Read `pages/show-and-tell.html` (also copied into the cache on `build`). That is the jam-session rundown.

## Run

```bash
python3 scripts/hum_https_broadcast.py build
python3 scripts/hum_https_broadcast.py cert
python3 scripts/hum_https_broadcast.py --host 127.0.0.1 --port 8443 serve
```

Open `https://127.0.0.1:8443/show-and-tell.html`. Pin `/cert.pem`.

If the virtio/LVM cache is mounted:

```bash
export HUM_LVM_CACHE=/mnt/virtual-drive/hum-cache
```

## systemctl concert

Copy `systemd/*.service` and `systemd/hum-housing.target` to `/etc/systemd/system/` on the desktop, then:

```bash
sudo systemctl daemon-reload
sudo systemctl start hum-housing.target
```
