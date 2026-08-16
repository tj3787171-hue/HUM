# Desktop agent show and tell

The live hypertext version is the source of truth:

- `site/broadcast/pages/show-and-tell.html`
- after build: `site/broadcast/cache/show-and-tell.html`
- while serving: `https://127.0.0.1:8443/show-and-tell.html`

You already have the posted transcript. You are on the virtio disk. The cloud-side agent broadcasts the cache over HTTPS, including the older wealth already in this image: telemetry, recup, palace, convo, cache assembly.

Join by dropping files into `HUM_LVM_CACHE` or `site/broadcast/cache`, then run `python3 scripts/hum_https_broadcast.py build`. Search `palace`, `recup`, or `telemetry` on `/wealth.html`.

Out of scope: dark-web entity lists, VNC-to-nbd0 attach, pentest scenes.
