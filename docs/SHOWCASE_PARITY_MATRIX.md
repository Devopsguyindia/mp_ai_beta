# Artwork showcase — parity matrix and phasing

Comparison to common “room preview / artwork mockup” products. This is a **planning** matrix, not a commitment date.

| Capability | MVP (this repo) | V1 | V2+ |
|------------|-----------------|----|-----|
| ERP item deep link | Yes (`/#/showcase/inventory?itemId=`) | Same | Same |
| Multi-image per SKU | Yes (dropdown) | Carousel / zoom | Batch select |
| CDN URL resolution | Yes (`company_item_pictures`) | Presigned private objects | Same |
| Scene library | Manifest JSON + QA fields | S3 thumbnails per scene | User-upload room |
| Presentation hints | Rules + optional LLM (`/showcase/options`) | Tune rules / prompts | Brand profiles |
| Pixel compositing / relight | **No** (`pass_through` + `cache_key`) | Compositor service | GPU / vendor API |
| Share / magic link | Stub (`/showcase/share`) | Token + TTL | Watermark + CRM |
| Packs / PDF export | No | Yes (planned) | White-label |
| Analytics | No | Optional events | Gallery dashboards |

## Phase alignment

| Phase | Deliverable |
|--------|-------------|
| **MVP** | Flags, `/showcase/*` APIs, manifest, options + render stub, widget shell, docs |
| **V1** | Real compositor, share tokens, multi-output packs |
| **V2+** | Branding, analytics, custom rooms |

## Isolation

V3 `/v3/ask`, module insights, and auth contracts remain unchanged when showcase is off. See `docs/ERP_SHOWCASE_INTEGRATION_GUIDE.md`.
