# Desktop agent show and tell

The live hypertext version is the source of truth:

- `site/broadcast/pages/show-and-tell.html`
- after build: `site/broadcast/cache/show-and-tell.html`
- while serving: `https://127.0.0.1:8443/show-and-tell.html`

You are on the virtio disk. The cloud-side agent broadcasts the cache over HTTPS. Join by dropping files into `HUM_LVM_CACHE` or `site/broadcast/cache`, then run `python3 scripts/hum_https_broadcast.py build`.

Out of scope: dark-web entity lists, VNC-to-nbd0 attach, pentest scenes.
