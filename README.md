# Personal research website

Built with Python, published free on GitHub Pages. Every change pushed to `main`
is tested and goes live in about a minute.

| To change…                         | Edit                                   |
|------------------------------------|----------------------------------------|
| Name, title, photo, profile links  | `site.yaml`                            |
| Page text                          | `content/<page>.md`                    |
| Extra / corrected publications     | `data/publications_manual.yaml`        |
| Photos, videos, PDFs               | `static/img`, `static/video`, `static/docs` |
| Data plots on pages                | `content/plots/<name>.yaml` + `[[plot:name]]` |
| Interactive calculators            | `tools/<slug>/tool.yaml` + `model.py` (+ `notes.md`) |

Shortcodes usable in any page: `[[figure:img/x.jpg|caption]]`, `[[youtube:ID|caption]]`,
`[[video:video/x.mp4|caption]]`, `[[pdf:docs/x.pdf|label]]`, `[[plot:name|caption]]`, `[[tool:slug]]`.

Local preview: `pip install -r requirements.txt && python build.py --drafts --serve`
