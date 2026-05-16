# Anime Scraper

Automatically fetches seasonal anime data from AniList every month.

## Live

| URL | Description |
|-----|-------------|
| `/` | Visual anime list |
| `/data.json` | Latest season JSON |
| `/history/YYYY-MM.json` | Archived months |

## JSON Format

```json
{
  "generated_at": "2026-01-31",
  "season": "Winter 2026",
  "total": 48,
  "anime": [
    {
      "name": "Title",
      "name_en": "English Title",
      "date": "Winter 2026",
      "start_date": "2026-01-05",
      "tag": "Action, Fantasy",
      "character": "Character A, Character B",
      "author": "Studio",
      "episodes": 12,
      "status": "RELEASING",
      "score": 82
    }
  ]
}
```

## Setup

Configure GitHub Secrets (`SMTP_USER`, `SMTP_PASS`, `TO_EMAIL`) and enable Pages from `main` / `docs`.

## Data Source

[AniList GraphQL API](https://anilist.gitbook.io/anilist-apiv2-docs/) — Free, no auth required.
