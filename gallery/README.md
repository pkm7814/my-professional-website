# Gallery — how to add or remove photos

```
gallery/
  international/<Country>/<Place>/   photos + _info.yaml
  india/<State>/<Place>/             photos + _info.yaml
```

- **New photos:** drop JPG/PNG/WebP files into the place folder. They are resized,
  turned upright and stripped of GPS/camera data automatically when the site is built.
- **New place / country / state:** create the folders and copy an `_info.yaml` from another place.
- **Remove:** delete the photo or folder (or set `hidden: true` in `_info.yaml`).
- **Captions:** in `_info.yaml` under `captions:` → `file-name.jpg: "Caption text"`.
- Order: most recent `date_sort` (YYYY-MM) first.
