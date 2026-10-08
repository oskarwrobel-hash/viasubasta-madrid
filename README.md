# Viasubasta Madrid — Automatic Auction Catalogue

A GitHub-ready scraper + static website for the public Viasubasta Madrid catalogue.

Source:
https://www.viasubasta.com/subastas-madrid/

## What it does

- Discovers all catalogue pages automatically.
- Opens individual auction/lot pages.
- Extracts title, reference, status, current bid, URL and images when available.
- Stores data in `data/auctions.json`.
- Downloads images into `data/images/`.
- Keeps `first_seen` / `last_seen` timestamps.
- Marks listings that disappear from the source as `not_seen`.
- Publishes the static website with GitHub Pages.
- Runs the scraper automatically using GitHub Actions.

## Important

Use this only for data that is publicly accessible and in accordance with Viasubasta's terms, robots.txt, copyright and applicable law. The project does not bypass login, CAPTCHA, access controls or other technical restrictions.

Do not commit credentials or API keys.

## Repository structure

```text
.
├── scraper.py
├── requirements.txt
├── data/
│   ├── auctions.json
│   └── images/
├── website/
│   ├── index.html
│   ├── app.js
│   └── style.css
└── .github/
    └── workflows/
        ├── scrape.yml
        └── pages.yml
```

## 1. Create the GitHub repository

Create a new repository, for example:

`viasubasta-madrid`

Upload the contents of this ZIP to the repository.

## 2. Enable GitHub Pages

In GitHub:

`Settings → Pages`

Choose:

- Source: **GitHub Actions**

The included `pages.yml` workflow publishes the `website/` directory.

## 3. Run the scraper manually first

On your computer:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scraper.py --dry-run
```

Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scraper.py --dry-run
```

Then test a real scrape:

```bash
python scraper.py --max-pages 2
```

For a full run:

```bash
python scraper.py --download-images
```

## 4. GitHub Actions

The scraper workflow is configured for every 30 minutes.

You can also run it manually from:

`Actions → Update Viasubasta Madrid → Run workflow`

The workflow commits changed JSON and images back to the repository.

## 5. Website

The website is completely static. It reads:

`data/auctions.json`

and displays:

- image
- title
- reference
- current bid
- status
- source link
- search
- category/status filters
- price filtering
- sorting
- responsive cards

## 6. Data format

Each auction is stored approximately as:

```json
{
  "id": "496",
  "reference": "496",
  "title": "Example auction",
  "status": "active",
  "current_bid": 815.0,
  "currency": "EUR",
  "image": "images/496/cover.jpg",
  "images": ["images/496/cover.jpg"],
  "url": "https://www.viasubasta.com/...",
  "first_seen": "2026-10-08T10:00:00Z",
  "last_seen": "2026-10-08T10:30:00Z"
}
```

## Notes about photos

The scraper tries to discover images from normal HTML metadata (`og:image`, image tags, JSON-LD and common gallery markup). Websites can change their HTML, so the selectors may need adjustment if Viasubasta changes its frontend.

## Recommended production setup

For a large image collection, move images/database to object storage or a database service rather than storing unlimited binary files in Git. The included GitHub version is intentionally simple and easy to understand.

## Troubleshooting

If the source starts returning 403/429 responses, do not try to bypass the restriction. Reduce request frequency and check the site's published rules/robots.txt.

If image extraction stops working, inspect one individual auction page and update the image selectors in `scraper.py`.

## License

This repository template is provided for your own use. Review Viasubasta's terms and the rights associated with any scraped content before republishing images or descriptions.
