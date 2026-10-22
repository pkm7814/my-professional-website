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
        for p in ("index.html", "about/index.html", "research/index.html", "publications/index.html",
                  "conferences/index.html", "contact/index.html", "tools/index.html", "404.html"):
            self.assertTrue((self.out / p).exists(), p)

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
            prefix = build.base_path(build.load_yaml(ROOT / "site.yaml", {}))
            for href in re.findall(r'(?:href|src|data-model)="(/[^"#?]*)"', page.read_text(encoding="utf-8")):
                self.assertTrue(href.startswith(prefix + "/"), f"link {href} misses the site prefix {prefix}")
                target = self.out / href[len(prefix):].lstrip("/")
                ok = target.exists() or (target / "index.html").exists()
                self.assertTrue(ok, f"broken link {href} in {page.relative_to(self.out)}")

    def test_no_secrets_or_private_details(self):
        # Guard against accidentally publishing passwords, phone numbers or a plain e-mail address.
        for page in self.pages:
            text = page.read_text(encoding="utf-8").lower()
            for bad in ("password", "secret_key", "7023146332", "@gmail.com"):
                self.assertNotIn(bad, text, f"{page.relative_to(self.out)} contains '{bad}'")

    def test_publications_listed_once(self):
        cats = build.load_publications()
        titles = [build.slugify(p["title"]) for _, items in cats for p in items]
        self.assertEqual(len(titles), len(set(titles)), "a publication appears twice")
        self.assertGreaterEqual(len(titles), 6)

    def test_gallery_photos_have_no_metadata(self):
        from PIL import Image
        for img in (self.out / "gallery").rglob("*.jpg"):
            with Image.open(img) as im:
                self.assertEqual(len(im.getexif()), 0, f"{img} still has EXIF/GPS data")
                self.assertLessEqual(max(im.size), 1600)

    def test_gallery_and_contact_form(self):
        g = (self.out / "gallery" / "index.html").read_text(encoding="utf-8")
        self.assertIn("International visits", g)
        self.assertIn("India", g)
        c = (self.out / "contact" / "index.html").read_text(encoding="utf-8")
        for field in ('name="name"', 'name="purpose"', 'name="message"', 'data-send="email"', 'data-send="whatsapp"'):
            self.assertIn(field, c)

    def test_external_links_are_safe(self):
        for page in self.pages:
            for tag in re.findall(r"<a [^>]*target=\"_blank\"[^>]*>", page.read_text(encoding="utf-8")):
                self.assertIn("noopener", tag, f"{page}: {tag}")


if __name__ == "__main__":
    unittest.main()
