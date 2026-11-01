"""Checks run on every deploy. If any fail, the live site is NOT updated.

    python -m unittest discover -s tests -v
"""
import html
import importlib.util
import math
import re
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import build  # noqa: E402

FIGURE_KEYS = {"series"}
STATUS = {"ok", "warn", "fail", "", None}


def load_model(slug):
    spec = importlib.util.spec_from_file_location(f"model_{slug}", ROOT / "tools" / slug / "model.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def finite_or_none(v):
    return v is None or isinstance(v, str) or (isinstance(v, (int, float)) and not math.isnan(v))


class ToolContracts(unittest.TestCase):
    """Every calculator returns the structure the web page expects, for its default inputs."""

    def test_all_tools(self):
        for cfg_path in sorted((ROOT / "tools").glob("*/tool.yaml")):
            slug = cfg_path.parent.name
            with self.subTest(tool=slug):
                cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
                names = [i["name"] for i in cfg["inputs"]]
                self.assertEqual(len(names), len(set(names)), "duplicate input names")
                for inp in cfg["inputs"]:
                    if inp.get("type", "number") == "number":
                        self.assertLessEqual(inp["min"], inp["default"])
                        self.assertLessEqual(inp["default"], inp["max"])
                res = load_model(slug).compute({i["name"]: i["default"] for i in cfg["inputs"]})
                self.assertIsInstance(res, dict)
                for s in res.get("summary", []):
                    self.assertIn("label", s)
                    self.assertIn(s.get("status"), STATUS)
                    self.assertTrue(finite_or_none(s["value"]), s)
                for f in res.get("figures", []):
                    self.assertTrue(FIGURE_KEYS <= f.keys())
                    for se in f["series"]:
                        self.assertEqual(len(se["x"]), len(se["y"]), se.get("name"))
                for t in res.get("tables", []):
                    for row in t["rows"]:
                        self.assertEqual(len(row), len(t["columns"]))


class InfiniteSlopeDemo(unittest.TestCase):
    """Verifies the analytical model against a hand calculation."""

    def test_dry_cohesionless_equals_tan_ratio(self):
        m = load_model("infinite-slope-demo")
        fs = m.factor_of_safety(c=0, phi=30, gamma=19, z=3, m=0, beta=25)["fs"]
        self.assertAlmostEqual(fs, math.tan(math.radians(30)) / math.tan(math.radians(25)), places=10)

    def test_water_reduces_fs(self):
        m = load_model("infinite-slope-demo")
        dry = m.factor_of_safety(5, 30, 19, 3, 0, 30)["fs"]
        wet = m.factor_of_safety(5, 30, 19, 3, 1, 30)["fs"]
        self.assertLess(wet, dry)


class BuiltSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = build.build(include_drafts=True)
        cls.pages = list(cls.out.rglob("*.html"))

    def test_pages_exist(self):
        # Every page in content/ is built (pages added or removed in the editor are fine).
        for p in ("index.html", "404.html", "admin/index.html"):
            self.assertTrue((self.out / p).exists(), p)
        for md in (ROOT / "content").glob("*.md"):
            url = "index.html" if md.stem == "home" else f"{md.stem}/index.html"
            self.assertTrue((self.out / url).exists(), f"page for {md.name} was not built")

    def test_security_headers_present(self):
        for page in self.pages:
            text = html.unescape(page.read_text(encoding="utf-8"))
            self.assertIn('http-equiv="Content-Security-Policy"', text, page)
            self.assertIn("object-src 'none'", text, page)

    def test_no_inline_executable_scripts(self):
        # CSP blocks inline scripts; every <script> must have src= or be JSON data.
        for page in self.pages:
            for tag in re.findall(r"<script[^>]*>", page.read_text(encoding="utf-8")):
                self.assertTrue("src=" in tag or 'type="application/json"' in tag, f"{page}: {tag}")

    def test_eval_only_on_calculator_pages(self):
        for page in self.pages:
            text = html.unescape(page.read_text(encoding="utf-8"))
            if "unsafe-eval" in text:
                self.assertIn('class="tool"', text, f"{page} allows eval but has no calculator")

    def test_internal_links_resolve(self):
        for page in self.pages:
            prefix = build.base_path(build.load_site())
            for href in re.findall(r'(?:href|src|data-model)="(/[^"#?]*)"', page.read_text(encoding="utf-8")):
                self.assertTrue(href.startswith(prefix + "/"), f"link {href} misses the site prefix {prefix}")
                target = self.out / href[len(prefix):].lstrip("/")
                ok = target.exists() or (target / "index.html").exists()
                self.assertTrue(ok, f"broken link {href} in {page.relative_to(self.out)}")

    def test_no_secrets_or_private_details(self):
        # Guard against accidentally publishing credentials (content wording is the owner's choice).
        for page in self.pages:
            text = page.read_text(encoding="utf-8").lower()
            self.assertNotIn("secret_key", text, f"{page.relative_to(self.out)} contains a secret key")
            self.assertIsNone(re.search(r"password\s*[:=]\s*\S", text), f"{page.relative_to(self.out)} looks like it contains a password")

    def test_publications_listed_once(self):
        cats = build.load_publications()
        titles = [build.slugify(p["title"]) for _, items in cats for p in items]
        self.assertEqual(len(titles), len(set(titles)), "a publication appears twice")

    def test_gallery_photos_have_no_metadata(self):
        from PIL import Image
        for img in (self.out / "gallery").rglob("*.jpg"):
            with Image.open(img) as im:
                self.assertEqual(len(im.getexif()), 0, f"{img} still has EXIF/GPS data")
                self.assertLessEqual(max(im.size), 1600)

    def test_gallery_shows_everything_in_the_data(self):
        gpage = self.out / "gallery" / "index.html"
        if not gpage.exists():
            return
        g = html.unescape(gpage.read_text(encoding="utf-8"))
        data = build.load_yaml(ROOT / "data" / "gallery.yaml", {}) or {}
        for alb in data.get("academic") or []:
            if alb and alb.get("name") and not alb.get("hidden"):
                self.assertIn(str(alb["name"]), g, f"gallery is missing {alb['name']}")
        for sec in ("international", "india"):
            groups = [x for x in (data.get(sec) or []) if x and not x.get("hidden")]
            for grp in groups:
                places = [pl for pl in (grp.get("places") or []) if pl and not pl.get("hidden")]
                if places:
                    self.assertIn(str(grp["name"]), g, f"gallery is missing {grp['name']}")
                for pl in places:
                    self.assertIn(str(pl["name"]), g, f"gallery is missing {pl['name']}")

    def test_every_album_has_a_page(self):
        gpage = self.out / "gallery" / "index.html"
        if not gpage.exists():
            return
        for href in re.findall(r'class="album" href="([^"]+)"', gpage.read_text(encoding="utf-8")):
            prefix = build.base_path(build.load_site())
            target = self.out / href[len(prefix):].lstrip("/") / "index.html"
            self.assertTrue(target.exists(), f"album page {href} missing")

    def test_contact_form_complete(self):
        for page in self.pages:
            c = page.read_text(encoding="utf-8")
            if 'id="contact-form"' not in c:
                continue
            for field in ('name="name"', 'name="purpose"', 'name="message"'):
                self.assertIn(field, c, f"{page}: contact form field {field} missing")
            self.assertIn('id="cf-purpose" name="purpose" type="text"', c, "purpose must be free text")
            self.assertIn("/js/contact.js", c)

    def test_admin_page_hidden_from_search(self):
        a = (self.out / "admin" / "index.html").read_text(encoding="utf-8")
        self.assertIn('name="robots" content="noindex', a)
        self.assertIn("app.pagescms.org", a)
        self.assertNotIn("/admin/", (self.out / "sitemap.xml").read_text())

    def test_every_page_section_is_known_to_editor_and_site(self):
        cfg = yaml.safe_load((ROOT / ".pages.yml").read_text(encoding="utf-8"))
        editor_types = {b["name"] for b in cfg["components"]["page_sections"]["blocks"]}
        template = (ROOT / "templates" / "_sections.html").read_text(encoding="utf-8")
        for t in editor_types:
            self.assertIn(f'"{t}"', template, f"section type {t} has no layout")
        for page in (ROOT / "content").glob("*.md"):
            meta, _ = build.split_front_matter(page.read_text(encoding="utf-8"))
            for sec in meta.get("sections") or []:
                self.assertIn(sec.get("type"), editor_types, f"{page.name}: unknown section {sec.get('type')}")

    def test_editor_media_folders_exist(self):
        cfg = yaml.safe_load((ROOT / ".pages.yml").read_text(encoding="utf-8"))
        for m in cfg["media"]:
            self.assertTrue((ROOT / m["input"]).is_dir(), f"media folder {m['input']} missing")

    def test_external_links_are_safe(self):
        for page in self.pages:
            for tag in re.findall(r"<a [^>]*target=\"_blank\"[^>]*>", page.read_text(encoding="utf-8")):
                self.assertIn("noopener", tag, f"{page}: {tag}")


if __name__ == "__main__":
    unittest.main()
