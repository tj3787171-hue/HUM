"""Render the blogspot circuit pages for the stdlib login server."""

from __future__ import annotations

import importlib.util
import json
import xml.etree.ElementTree as ET
from html import escape
from pathlib import Path

CIRCUITS_ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = CIRCUITS_ROOT.parent
SCRIPTS = SITE_ROOT.parent / "scripts"


def _load_zones_mod():
    path = SCRIPTS / "hum-isolation-zones.py"
    spec = importlib.util.spec_from_file_location("hum_isolation_zones", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load hum-isolation-zones.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


zones = _load_zones_mod()


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def load_posts() -> list[dict[str, str]]:
    path = CIRCUITS_ROOT / "data" / "posts.xml"
    posts: list[dict[str, str]] = []
    with path.open("rb") as handle:
        root = ET.parse(handle).getroot()
    for child in root:
        if _local(child.tag) != "post":
            continue
        fields = {_local(item.tag): (item.text or "") for item in child}
        posts.append(
            {
                "id": child.attrib.get("id", ""),
                "slug": child.attrib.get("slug", ""),
                "date": child.attrib.get("date", ""),
                "title": fields.get("title", ""),
                "body": fields.get("body", ""),
            }
        )
    return posts


def load_catalog() -> dict:
    path = CIRCUITS_ROOT / "data" / "iso-catalog.json"
    return json.loads(path.read_text(encoding="utf-8"))


def page(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{escape(title)}</title>
  <link rel="stylesheet" href="/assets/login.css"/>
  <link rel="stylesheet" href="/circuits/assets/circuits.css"/>
</head>
<body>
<header>
  <span class="logo">HUM.org</span>
  <nav>
    <a href="/circuits/">Blog</a>
    <a href="/circuits/iso">ISOs</a>
    <a href="/circuits/zones">Zones</a>
    <a href="/circuits/risk">NBD risk</a>
    <a href="/login">Login</a>
  </nav>
</header>
<div class="container auth-wrap">
{body}
</div>
<footer>HUM.org circuits &middot; blogspot delivery &middot; VNC stays off nbd0</footer>
</body>
</html>
"""


def blog() -> str:
    articles = []
    for post in load_posts():
        articles.append(
            "<article class='panel'>"
            f"<h2>{escape(post['title'])}</h2>"
            f"<p class='lede'>{escape(post['date'])} &middot; {escape(post['slug'])}</p>"
            f"<p>{escape(post['body'])}</p>"
            "</article>"
        )
    body = (
        "<section class='panel'><h1>Circuit blog</h1>"
        "<p class='lede'>Simple delivery. Virtio vda on /dev/sda. One login. Dummy rails. VNC never joins nbd0.</p>"
        "</section>"
        + "".join(articles)
    )
    return page("HUM circuits", body)


def iso_page() -> str:
    catalog = load_catalog()
    rows = []
    for item in catalog.get("isos", []):
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('id', '')))}</td>"
            f"<td>{escape(str(item.get('title', '')))}</td>"
            f"<td>{escape(str(item.get('phase', '')))}</td>"
            f"<td>{escape(str(item.get('family', '')))}</td>"
            f"<td>{'yes' if item.get('bundle') else 'no'}</td>"
            "</tr>"
        )
    body = (
        "<section class='panel'><h1>ISO tracks</h1>"
        f"<p class='lede'>Guest {escape(str(catalog.get('guest_disk')))} maps host {escape(str(catalog.get('host_disk')))}.</p>"
        "<table><thead><tr><th>ID</th><th>Title</th><th>Phase</th><th>Family</th><th>Bundled</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></section>"
    )
    return page("ISO tracks", body)


def zones_page() -> str:
    catalog = load_catalog()
    present = sum(1 for item in catalog.get("isos", []) if item.get("phase") == "present")
    plan = zones.allocate_zones(max(1, present), catalog)
    rows = []
    for guest in plan["guests"]:
        rows.append(
            "<tr>"
            f"<td>{escape(guest['track'])}</td>"
            f"<td>{escape(guest['dummy_rail'])}</td>"
            f"<td>{guest['display_zone']}</td>"
            f"<td>{escape(guest['vnc_bind'])}:{guest['vnc_port']}</td>"
            f"<td>{guest['disk_zone']}</td>"
            "</tr>"
        )
    body = (
        "<section class='panel'><h1>Isolation zones</h1>"
        f"<p class='lede'>Housing {escape(plan['housing'])}. nbd0 zone {plan['nbd0']['zone']} attach {escape(plan['nbd0']['vnc_attach'])}.</p>"
        "<table><thead><tr><th>Track</th><th>Dummy rail</th><th>Display zone</th><th>VNC</th><th>Disk zone</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></section>"
    )
    return page("Isolation zones", body)


def risk_page() -> str:
    body = """
  <section class="panel">
    <h1>nbd0 is a high-risk collision, not a VNC target</h1>
    <p class="lede">This page is isolation policy. It does not attach, probe, or exploit VNC or NBD.</p>
    <table>
      <tbody>
        <tr><th>Block export</th><td><code>/dev/nbd0</code> zone 300</td></tr>
        <tr><th>Display path</th><td>VNC on <code>127.0.0.1</code> zones 100+</td></tr>
        <tr><th>Attach</th><td>denied</td></tr>
      </tbody>
    </table>
  </section>
"""
    return page("NBD / VNC risk", body)
