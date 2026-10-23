#!/usr/bin/env python3
"""
Build the website into the _site/ folder.

    python build.py              # normal build (fetches integrity hashes if online)
    python build.py --strict     # CI build: fail if any library URL cannot be verified
    python build.py --drafts     # also include pages/tools marked `draft: true`
    python build.py --serve      # build, then preview at http://localhost:8000

Content lives in:
    site.yaml            name, links, menu, library versions
    content/*.md         one Markdown file per page (front matter at the top)
    content/plots/*.yaml data plots embedded with [[plot:name]]
    data/*.yaml          publications (ORCID auto + manual extras)
    tools/<slug>/        interactive calculators: tool.yaml + model.py
    static/              css, js, images, videos, documents
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import re
import shutil
import sys
import urllib.request
from datetime import date
from pathlib import Path

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "_site"
SRI_CACHE = ROOT / ".sri-cache.json"

# ------------------------------------------------------------------ helpers


def load_yaml(path: Path, default=None):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return default if data is None else data


def split_front_matter(text: str) -> tuple[dict, str]:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return (yaml.safe_load(parts[1]) or {}), parts[2].lstrip("\n")
    return {}, text


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


# ------------------------------------------------------- library URLs + SRI


def library_urls(libs: dict) -> dict:
    p, py, k = libs["plotly"], libs["pyodide"], libs["katex"]
    return {
        "plotly": f"https://cdn.jsdelivr.net/npm/plotly.js-dist-min@{p}/plotly.min.js",
        "pyodide": f"https://cdn.jsdelivr.net/pyodide/v{py}/full/pyodide.js",
        "pyodide_index": f"https://cdn.jsdelivr.net/pyodide/v{py}/full/",
        "katex_css": f"https://cdn.jsdelivr.net/npm/katex@{k}/dist/katex.min.css",
        "katex_js": f"https://cdn.jsdelivr.net/npm/katex@{k}/dist/katex.min.js",
        "katex_auto": f"https://cdn.jsdelivr.net/npm/katex@{k}/dist/contrib/auto-render.min.js",
    }


def compute_sri(urls: dict, strict: bool) -> dict:
    """Return {url: 'sha384-...'} so the browser refuses tampered CDN files."""
    cache = json.loads(SRI_CACHE.read_text()) if SRI_CACHE.exists() else {}
    result, changed = {}, False
    for key, url in urls.items():
        if url.endswith("/"):
            continue
        if url in cache:
            result[url] = cache[url]
            continue
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                digest = hashlib.sha384(resp.read()).digest()
            cache[url] = result[url] = "sha384-" + base64.b64encode(digest).decode()
            changed = True
        except Exception as exc:  # offline or bad version
            msg = f"could not fetch {url}: {exc}"
            if strict:
                sys.exit(f"ERROR: {msg}\nCheck the version numbers under `libs:` in site.yaml.")
            print(f"warning: {msg} (integrity hash skipped for this local build)")
    if changed:
        SRI_CACHE.write_text(json.dumps(cache, indent=2, sort_keys=True))
    return result


# ------------------------------------------------------------ Content Security


def csp(needs_python: bool) -> str:
    script = "'self' https://cdn.jsdelivr.net"
    if needs_python:
        # Pyodide runs Python as WebAssembly; only calculator pages get this.
        script += " 'wasm-unsafe-eval' 'unsafe-eval'"
    return "; ".join([
        "default-src 'self'",
        f"script-src {script}",
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "font-src 'self' data: https://cdn.jsdelivr.net",
        "img-src 'self' data: https:",
        "media-src 'self' https:",
        "connect-src 'self' https://cdn.jsdelivr.net",
        "frame-src https://www.youtube-nocookie.com https://player.vimeo.com",
        "worker-src 'self' blob:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'none'",
        "upgrade-insecure-requests",
    ])


# ------------------------------------------------------------------- tools


def load_tools(include_drafts: bool) -> dict:
    tools = {}
    for cfg_path in sorted((ROOT / "tools").glob("*/tool.yaml")):
        cfg = load_yaml(cfg_path, {})
        if cfg.get("draft") and not include_drafts:
            continue
        slug = cfg_path.parent.name
        cfg["slug"] = slug
        cfg.setdefault("title", slug.replace("-", " ").title())
        cfg.setdefault("packages", [])
        for inp in cfg.get("inputs", []):
            inp.setdefault("type", "number")
            inp.setdefault("label", inp["name"])
            inp.setdefault("unit", "")
        tools[slug] = cfg
    return tools


# ------------------------------------------------------------ shortcodes


class Shortcodes:
    """[[youtube:ID]] [[vimeo:ID]] [[video:file.mp4|caption]] [[figure:img.jpg|caption]]
    [[tool:slug]] [[plot:name]] [[pdf:file.pdf|label]]"""

    # Code is left untouched; math is protected from Markdown (which eats backslashes);
    # shortcodes are replaced by rendered HTML.
    PATTERN = re.compile(
        r"(?P<fence>```.*?```)"
        r"|(?P<code>`[^`\n]+`)"
        r"|(?P<dmath>\$\$.+?\$\$|\\\[.+?\\\])"
        r"|(?P<imath>\\\(.+?\\\))"
        r"|\[\[(?P<kind>\w+):(?P<arg>[^\]|]+)(?:\|(?P<cap>[^\]]*))?\]\]",
        re.S,
    )

    def __init__(self, env, tools: dict, include_drafts: bool):
        self.env, self.tools, self.include_drafts = env, tools, include_drafts

    def expand(self, body: str):
        blocks, flags = {}, {"python": False, "plot": False, "math": False}

        def stash(html_text, block):
            token = f"SHORTCODE{len(blocks):04d}X"
            blocks[token] = html_text
            return f"\n\n{token}\n\n" if block else token

        def repl(m):
            if m.group("fence") or m.group("code"):
                return m.group(0)
            if m.group("dmath"):
                flags["math"] = True
                return stash(f'<div class="math">{html.escape(m.group("dmath"))}</div>', True)
            if m.group("imath"):
                flags["math"] = True
                return stash(html.escape(m.group("imath")), False)
            kind, arg, cap = m.group("kind").lower(), m.group("arg").strip(), (m.group("cap") or "").strip()
            return stash(self.render(kind, arg, cap, flags), True)

        return self.PATTERN.sub(repl, body), blocks, flags

    def render(self, kind, arg, cap, flags):
        e = html.escape
        caption = f"<figcaption>{e(cap)}</figcaption>" if cap else ""
        if kind == "youtube":
            src = f"https://www.youtube-nocookie.com/embed/{e(arg)}"
            return (f'<figure class="embed"><div class="ratio"><iframe src="{src}" title="{e(cap or "Video")}" '
                    'loading="lazy" allow="encrypted-media; picture-in-picture" allowfullscreen '
                    f'referrerpolicy="strict-origin-when-cross-origin"></iframe></div>{caption}</figure>')
        if kind == "vimeo":
            src = f"https://player.vimeo.com/video/{e(arg)}"
            return (f'<figure class="embed"><div class="ratio"><iframe src="{src}" title="{e(cap or "Video")}" '
                    f'loading="lazy" allowfullscreen></iframe></div>{caption}</figure>')
        if kind == "video":
            return (f'<figure class="embed"><video controls preload="metadata" src="/{e(arg.lstrip("/"))}">'
                    f"</video>{caption}</figure>")
        if kind == "figure":
            return (f'<figure><img src="/{e(arg.lstrip("/"))}" alt="{e(cap)}" loading="lazy">{caption}</figure>')
        if kind == "pdf":
            return f'<a class="button" href="/{e(arg.lstrip("/"))}" download>{e(cap or "Download PDF")}</a>'
        if kind == "tool":
            tool = self.tools.get(arg)
            if not tool:
                return f'<p class="notice">Tool “{e(arg)}” is not published yet.</p>'
            flags["python"] = flags["plot"] = True
            return self.env.get_template("_tool.html").render(tool=tool)
        if kind == "plot":
            spec = load_yaml(ROOT / "content" / "plots" / f"{arg}.yaml")
            if spec is None:
                return f'<p class="notice">Plot “{e(arg)}” not found.</p>'
            flags["plot"] = True
            data = json.dumps(spec).replace("</", "<\\/")
            return (f'<figure class="plot-static"><div class="plot" data-plot></div>'
                    f'<script type="application/json" class="plot-spec">{data}</script>{caption}</figure>')
        return f'<p class="notice">Unknown shortcode “{e(kind)}”.</p>'


# ----------------------------------------------------------- publications


PUB_CATEGORIES = [  # (heading, ORCID/manual types that belong to it)
    ("Journal articles", {"journal-article", "journal"}),
    ("Conference papers", {"conference-paper", "conference", "conference-proceedings", "conference-abstract"}),
    ("Book chapters", {"book-chapter", "book"}),
    ("Other works", set()),
]


def load_publications(highlight: str = "") -> list[dict]:
    """Merge ORCID works with the hand-curated list.

    The manual list (data/publications_manual.yaml) is authoritative: it can add
    authors, fix titles, or hide an ORCID item. Works are matched by DOI or by
    title (ignoring case and punctuation) so the same paper never appears twice.
    """
    auto = load_yaml(ROOT / "data" / "publications_orcid.yaml", []) or []
    manual = load_yaml(ROOT / "data" / "publications_manual.yaml", []) or []
    merged: list[dict] = []
    index: dict[str, dict] = {}

    def keys(p):
        k = []
        if p.get("doi"):
            k.append("doi:" + str(p["doi"]).lower().strip())
        for t in (p.get("title"), p.get("match_title")):
            if t:
                k.append("t:" + slugify(t))
        return k

    for src in (auto, manual):
        for pub in src:
            clean = {k: v for k, v in pub.items() if v not in (None, "")}
            target = next((index[k] for k in keys(clean) if k in index), None)
            if target is None:
                target = {}
                merged.append(target)
            target.update(clean)
            for k in keys(target):
                index[k] = target

    pubs = [p for p in merged if not p.get("hidden")]
    for p in pubs:
        authors = html.escape(str(p.get("authors", "")))
        if highlight and authors:
            authors = authors.replace(html.escape(highlight), f"<strong>{html.escape(highlight)}</strong>")
        p["authors_html"] = authors
        t = str(p.get("type", "")).lower()
        p["category"] = next((name for name, types in PUB_CATEGORIES if t in types), "Other works")
    pubs.sort(key=lambda p: (int(p.get("year") or 0), p.get("title", "")), reverse=True)
    order = [name for name, _ in PUB_CATEGORIES]
    return [(name, [p for p in pubs if p["category"] == name]) for name in order
            if any(p["category"] == name for p in pubs)]


# ------------------------------------------------------------ base path


def base_path(site: dict) -> str:
    """'/my-professional-website' for https://user.github.io/my-professional-website, '' for a root site."""
    from urllib.parse import urlparse
    return urlparse(site.get("base_url") or "").path.rstrip("/")


ROOT_LINK = re.compile(r'(\s(?:href|src|data-model|action|poster)=")/(?!/)')


def prefix_paths(page_html: str, prefix: str) -> str:
    return ROOT_LINK.sub(lambda m: f"{m.group(1)}{prefix}/", page_html) if prefix else page_html


# ---------------------------------------------------------------- gallery
#
# data/gallery.yaml (edited in the admin editor):
#   international: [ {name: Country, places: [ {name, date, event, description,
#                     photos: [ {image: /gallery-photos/x.jpg, caption} ]} ]} ]
#   india:         [ {name: State,   places: [...]} ]
# Photo files live in gallery/photos/. They are resized (1600 px + 600 px
# thumbnail), turned upright and stripped of all metadata (incl. GPS) on build.

GALLERY_PHOTOS = ROOT / "gallery" / "photos"
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp"}


def _process_photo(src: Path, dest_dir: Path, stem: str) -> dict:
    from PIL import Image, ImageOps
    dest_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        out = {}
        for key, size, quality in (("full", 1600, 84), ("thumb", 600, 80)):
            copy = im.copy()
            copy.thumbnail((size, size))
            path = dest_dir / f"{stem}-{key}.jpg"
            copy.save(path, "JPEG", quality=quality, optimize=True, progressive=True)  # no EXIF written
            out[key] = "/" + str(path.relative_to(OUT)).replace("\\", "/")
            out[f"{key}_size"] = copy.size
    return out


def _photo_source(ref: str) -> Path | None:
    """Map an editor value such as '/gallery-photos/osaka 1.jpg' to gallery/photos/osaka 1.jpg."""
    name = str(ref or "").replace("\\", "/").split("/")[-1]
    path = GALLERY_PHOTOS / name
    return path if name and path.suffix.lower() in PHOTO_TYPES and path.exists() else None


def build_gallery(out_dir: Path) -> list[dict]:
    data = load_yaml(ROOT / "data" / "gallery.yaml", {}) or {}
    sections, done = [], {}
    for key, default_title in (("international", "International visits"), ("india", "India — home country visits")):
        groups = []
        for g in data.get(key) or []:
            if not g or not g.get("name") or g.get("hidden"):
                continue
            gid = f"{key}-{slugify(g['name'])}"
            places = []
            for pl in g.get("places") or []:
                if not pl or not pl.get("name") or pl.get("hidden"):
                    continue
                pid = f"{gid}-{slugify(pl['name'])}"
                photos = []
                for i, ph in enumerate(pl.get("photos") or [], 1):
                    ref = ph.get("image") if isinstance(ph, dict) else ph
                    caption = (ph.get("caption") if isinstance(ph, dict) else "") or ""
                    src = _photo_source(ref)
                    if src is None:
                        print(f"warning: gallery photo not found: {ref}")
                        continue
                    if src not in done:
                        done[src] = _process_photo(src, out_dir, slugify(src.stem) or f"photo-{len(done)+1}")
                    res = done[src]
                    photos.append({"full": res["full"], "thumb": res["thumb"],
                                   "w": res["thumb_size"][0], "h": res["thumb_size"][1], "caption": caption,
                                   "alt": caption or f"{pl['name']}, {g['name']} — photo {i}"})
                places.append({"id": pid, "title": pl["name"], "info": pl, "photos": photos})
            if places:
                groups.append({"id": gid, "title": g["name"], "places": places})
        if groups:
            sections.append({"id": key, "title": data.get(f"{key}_heading") or default_title, "groups": groups})
    return sections


# ---------------------------------------------------------- site settings


def load_site() -> dict:
    """Technical settings (site.yaml) + everything editable (data/profile.yaml)."""
    site = load_yaml(ROOT / "site.yaml", {}) or {}
    site.update(load_yaml(ROOT / "data" / "profile.yaml", {}) or {})
    # Citation numbers: typed-in Google Scholar figures win; otherwise automatic OpenAlex ones.
    manual = site.get("scholar_metrics") or {}
    auto = load_yaml(ROOT / "data" / "metrics_auto.yaml", {}) or {}
    if manual.get("citations") not in (None, ""):
        site["metrics"] = dict(manual, source="Google Scholar")
    elif auto.get("citations"):
        site["metrics"] = auto
    else:
        site["metrics"] = {}
    email = str(site.get("email") or "")
    site["email_user"], _, site["email_domain"] = email.partition("@")
    wa = re.sub(r"\D", "", str(site.get("whatsapp") or ""))
    site["wa_p1"], site["wa_p2"] = wa[: len(wa) // 2], wa[len(wa) // 2:]
    return site


def asset(value) -> str:
    """Normalise an image/file path from the editor to '/path' (external URLs unchanged)."""
    v = str(value or "").strip()
    if not v or re.match(r"^(https?:|mailto:|tel:|#)", v):
        return v
    return "/" + v.lstrip("/")


def youtube_id(value) -> str:
    v = str(value or "").strip()
    m = re.search(r"(?:youtu\.be/|v=|embed/|shorts/)([\w-]{6,})", v)
    return m.group(1) if m else (v if re.fullmatch(r"[\w-]{6,}", v) else "")


# ------------------------------------------------------------------ build


def build(include_drafts=False, strict=False) -> Path:
    site = load_site()
    urls = library_urls(site["libs"])
    sri = compute_sri(urls, strict)
    tools = load_tools(include_drafts)

    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "attr_list",
                                       "md_in_html", "footnotes", "sane_lists"])

    def md_block(text) -> Markup:
        md.reset()
        return Markup(md.convert(str(text or "")))

    def md_inline(text) -> Markup:
        out = str(md_block(text)).strip()
        if out.startswith("<p>") and out.endswith("</p>") and out.count("<p>") == 1:
            out = out[3:-4]
        return Markup(out)

    env = Environment(loader=FileSystemLoader(ROOT / "templates"),
                      autoescape=select_autoescape(["html"]))
    env.globals.update(site=site, lib=urls, sri=sri, year=date.today().year)
    env.filters.update(md=md_block, mdi=md_inline, asset=asset, youtube_id=youtube_id)
    shortcodes = Shortcodes(env, tools, include_drafts)
    prefix = base_path(site)

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "static", OUT)
    (OUT / ".nojekyll").write_text("")

    pages_written = []

    def write(url: str, template: str, needs_python=False, **ctx):
        dest = OUT / url.strip("/") / "index.html" if url != "/404.html" else OUT / "404.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        html_out = env.get_template(template).render(
            url=url, csp=csp(needs_python), needs_python=needs_python, **ctx)
        dest.write_text(prefix_paths(html_out, prefix), encoding="utf-8")
        if url != "/404.html" and not ctx.get("noindex"):
            pages_written.append(url)

    special = {"home": "home.html", "publications": "publications.html", "gallery": "gallery.html"}

    # Pages: front matter (title, subtitle, header image, sections) + optional Markdown body
    for path in sorted((ROOT / "content").glob("*.md")):
        meta, body = split_front_matter(path.read_text(encoding="utf-8"))
        if meta.get("draft") and not include_drafts:
            continue
        body, blocks, flags = shortcodes.expand(body)
        md.reset()
        content = md.convert(body)
        for token, block in blocks.items():
            content = content.replace(f"<p>{token}</p>", block).replace(token, block)
        sections = [s for s in (meta.get("sections") or []) if isinstance(s, dict) and not s.get("hidden")]
        has_math = bool(meta.get("math") or flags["math"])
        url = "/" if path.stem == "home" else f"/{path.stem}/"
        template = special.get(path.stem) or (meta.get("template", "page") + ".html")
        extra = {}
        if template == "publications.html":
            extra["publications"] = load_publications(site.get("highlight_author", ""))
        if template == "gallery.html":
            extra["gallery"] = build_gallery(OUT / "gallery")
        write(url, template, needs_python=flags["python"], page=meta, content=content, sections=sections,
              needs_plot=flags["plot"], needs_math=has_math,
              needs_contact=any(s.get("type") == "contact_form" for s in sections), **extra)

    # Tools: index + one page each
    write("/tools/", "tools_index.html", page={"title": "Tools"}, tools=tools.values())
    for slug, tool in tools.items():
        tool_dir = ROOT / "tools" / slug
        (OUT / "tools" / slug).mkdir(parents=True, exist_ok=True)
        shutil.copy(tool_dir / "model.py", OUT / "tools" / slug / "model.py")
        notes_html, notes_math = "", False
        if (tool_dir / "notes.md").exists():
            body, blocks, flags = shortcodes.expand((tool_dir / "notes.md").read_text(encoding="utf-8"))
            md.reset()
            notes_html = md.convert(body)
            for token, block in blocks.items():
                notes_html = notes_html.replace(f"<p>{token}</p>", block).replace(token, block)
            notes_math = flags["math"]
        write(f"/tools/{slug}/", "tool_page.html", needs_python=True, page={"title": tool["title"]},
              tool=tool, notes=notes_html, needs_plot=True, needs_math=notes_math)

    write("/admin/", "admin.html", page={"title": "Admin", "description": "Site administration."}, noindex=True)
    write("/404.html", "page.html", page={"title": "Page not found"}, sections=[],
          content='<p>Sorry, that page does not exist. <a href="/">Go to the home page</a>.</p>')

    # sitemap + robots
    base = (site.get("base_url") or "").rstrip("/")
    if base:
        items = "".join(f"<url><loc>{base}{u}</loc></url>" for u in pages_written)
        (OUT / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>')
    (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\nDisallow: " + (prefix or "") + "/admin/\n" +
                                    (f"Sitemap: {base}/sitemap.xml\n" if base else ""))
    print(f"Built {len(pages_written)} pages and {len(tools)} tool(s) into {OUT.relative_to(ROOT)}/")
    return OUT


def serve(port=8000):
    import functools
    import http.server
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(OUT))
    print(f"Preview: http://localhost:{port}  (Ctrl+C to stop)")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--drafts", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--serve", action="store_true")
    args = ap.parse_args()
    build(include_drafts=args.drafts, strict=args.strict)
    if args.serve:
        serve()
