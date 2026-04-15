# Artwork showcase — data contract

This document summarizes ERP tables and URL rules used by **`/showcase/*`** APIs. Showcase SQL lives only under `copilot-api/app/showcase/` (not in V3 NL2SQL).

## `company_item_pictures`

The showcase loader **only references** these columns on `company_item_pictures`:

| Column | Usage |
|--------|--------|
| `idcompany_item_pictures` | Primary key; selection and render cache. |
| `idcompany` | Tenant filter in `WHERE`. |
| `idcompany_item` | Item FK. |
| `picture` | Filename fragment for CDN URL. |
| `server_path` | Path prefix for CDN URL. |

No `is_deleted`, `is_primary`, `rank`, `seq_no`, `thumbnail_url`, or other columns are read. Rows are ordered by **`idcompany_item_pictures`** ascending.

## `company_item`

Joined for `title` and `edition_type` (presentation context). **No** `is_delete` / `is_deleted` filters are applied on `company_item` or `company_item_pictures`.

## `company_item_data` (view)

**LEFT JOIN** for display hints: `EditionName`, `ArtName`. If this view is unavailable in an environment, adjust `pictures_repo.py` (showcase-only).

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
