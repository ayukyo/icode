# Public website source

The site is deliberately static: two HTML pages, one stylesheet, and the original ICODE brand assets. It uses no JavaScript, external CDN, analytics, tracker, login, or ticket data.

Preview from the repository root:

```bash
python3 scripts/check_site.py
python3 -m http.server 8000 --directory site
```

Then open <http://127.0.0.1:8000/>. GitHub Actions validates the same source and can deploy it to GitHub Pages after Pages is enabled for this repository.
