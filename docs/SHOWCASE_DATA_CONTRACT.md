# Artwork showcase — data contract

This document summarizes ERP tables and URL rules used by **`/showcase/*`** APIs. Showcase SQL lives only under `copilot-api/app/showcase/` (not in V3 NL2SQL).

## `company_item_pictures`

| Column | Usage |
|--------|--------|
| `idcompany_item_pictures` | Primary key; used in render **cache keys** and UI selection. |
| `idcompany`, `idcompany_item` | Tenant + item FK. |
| `picture`, `server_path` | URL fragments; resolved with `MP_ASSET_CDN_BASE`. |
| `is_deleted` | Rows with `1` excluded (`COALESCE(is_deleted,0)=0`). |
| `is_primary`, `rank`, `seq_no` | Sort: primary first, then rank, seq, id. |
| `thumbnail_url` | Optional; must pass same host allowlist as main URL when set. |

## `company_item`

Joined for `title`, `edition_type`, and soft-delete (`is_delete`).

## `company_item_data` (view)

**LEFT JOIN** for display and presentation hints: `EditionName`, `ArtName`.

If this view is unavailable in an environment, operators must adjust `pictures_repo.py` (showcase-only).

## Category / medium

Dedicated ERP columns for **category** and **medium** are not assumed in MVP SQL. The API may return:

- **Heuristic** `category_label` / `medium_label` inferred from title/artist text (soft hints).
- **Edition** context via `edition_label` / `item_edition_type` from inventory.

Future: extend the SELECT with your gallery’s category/medium tables in **`pictures_repo.py`** only.

## Public URL

```
resolved_url = normalize( MP_ASSET_CDN_BASE + server_path + picture )
```

Optional: `SHOWCASE_ASSET_HOST_ALLOWLIST` restricts hosts.

## QA sample URLs (CDN)

Non-secret examples for pipeline QA (replace if expired):

- `https://masterpiece.s3.amazonaws.com/HTECB2KD981771712543.jpg`
- `https://masterpiece.s3.amazonaws.com/ggkQ3EzBkq1775845716.jpg`
- `https://masterpiece.s3.amazonaws.com/49Hxsnh8oQ1775764442.jpg`
- `https://masterpiece.s3.amazonaws.com/EB2vs03hw51775848324.jpg`

## Scene library manifest

Runtime list: `app/showcase/data/scene_library_manifest.json` (or `SHOWCASE_SCENE_MANIFEST_PATH` / `SHOWCASE_SCENE_MANIFEST_JSON`).

Batch workflow: generate → QA → upload **`preview_asset_url`** to S3 → bump **`pipeline_version`** → deploy manifest.
