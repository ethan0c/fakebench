# FakeBench

**Can you tell real photos from AI?** FakeBench gives players 20 images and five seconds to decide on each. Results include a score, an estimated percentile, and a review of missed images. The site also shows average accuracy over the past seven days. Workflows handle weekly content refreshes and daily posts once they're configured.

The image test is at `/image`. Text, voice and face tests are listed on the home page but aren't available yet. The engine can support additional test types.

## How it works

| Piece | What it does |
|---|---|
| `public/` | Static pages and the game (`image.html` and `app.js`): 20 images, 5 seconds each, immediate feedback, an estimated percentile, a review of missed images with model names or photo credits, share links, and a daily challenge with streaks. |
| `src/index.js` | Cloudflare Worker. `/api/round` builds a round (daily rounds are seeded by the UTC date so everyone gets the same 10). `/api/result` stores the score and returns a percentile from a histogram. `/api/stats` is the live human-accuracy stat. `/og/*.png` renders share cards and video overlays with satori (no browser). `/share/...` is the link-preview page. A nightly cron rolls results into `daily_rollup`. |
| `schema/schema.sql` | D1 tables: `results`, `score_hist` (percentiles without table scans), `item_stats` (which images fool people), `daily_rollup`. |
| `scripts/extract_parquet.py` | Primary AI-image source. Reads Rapidata's per-model preference datasets (CDLA-Permissive-2.0) straight from their parquet shards on the HF CDN, so there is no API rate limit. Every image has its generating model recorded. `scripts/fetch_fake.py` is the rows-API fallback (slow without `HF_TOKEN`). |
| `scripts/filters.py` | Filters out prompts and models unlikely to produce a plausible photo. Runs during fetching and manifest builds, so the rules can change without downloading the images again. |
| `scripts/fetch_real.py` | Pulls real photos from Wikimedia Commons (CC0 / PD / CC BY / CC BY-SA only), using the AI prompts as search queries so subjects match. Stores credit + license, shown in the reveal. |
| `scripts/generate_fake.py` | Optional: generates AI images through fal.ai when `FAL_KEY` is set. Costs depend on the configured models. |
| `scripts/build_manifest.py` | Crops every image to the same square size, uses the same JPEG settings, and removes metadata to reduce clues from file formatting. Writes `public/media/manifest.json`. |
| `scripts/make_video.py` | Renders the daily vertical "Real or AI?" video (1080x1920) with ffmpeg; text overlays come from the Worker so no fonts are needed. |
| `scripts/post_stat.py` | Posts the live stat to Bluesky and X, and schedules the video to TikTok / Reels / Shorts through Postiz. Each channel is on only when its secrets exist. |
| `.github/workflows/` | `deploy.yml` on push. `refresh-content.yml` weekly (Mon 00:05 UTC). `marketing.yml` daily (15:00 UTC). |

Percentiles combine submitted scores with a starting estimate: a binomial distribution with p = 0.62 and a weight of 40 rounds. This keeps the earliest rankings from depending on just a few results. Its influence decreases as more rounds are played. Ties receive the midpoint rank; daily and regular rounds use separate score distributions. Rankings describe submitted rounds rather than unique players.

## Run locally

```bash
npm install
python3 -m venv .venv && .venv/bin/pip install pyarrow
.venv/bin/python3 -I scripts/extract_parquet.py --shards random:4 --count 150
python3 -I scripts/fetch_real.py --count 150
python3 -I scripts/build_manifest.py
npx wrangler d1 execute fakebench --local --file schema/schema.sql
npx wrangler dev
```

Then open http://localhost:8787/image. The Worker logs a harmless "Already initialized" line from `workers-og` on every share-card render in dev.

## Deploy

1. Create the database and paste its id into `wrangler.jsonc`:
   ```bash
   npx wrangler d1 create fakebench
   npx wrangler d1 execute fakebench --remote --file schema/schema.sql
   npx wrangler deploy
   ```
2. Set `SITE_URL` in `wrangler.jsonc` (and the `canonical`/`sitemap` URLs in `public/`) to your domain once it is attached to the Worker.
3. Push to GitHub. Add repository secrets `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`, and a repository variable `SITE_URL`. Every push to `main` deploys.
4. Optional secrets, each unlocking one automation: `HF_TOKEN` (faster content refresh), `FAL_KEY` (fresh fakes from current models), `BSKY_HANDLE` + `BSKY_APP_PASSWORD`, `X_API_KEY` + `X_API_SECRET` + `X_ACCESS_TOKEN` + `X_ACCESS_SECRET`, `POSTIZ_API_KEY` + variable `POSTIZ_INTEGRATIONS` (comma-separated Postiz channel ids for TikTok, Instagram, YouTube).

The `unsafe.bindings` rate limit in `wrangler.jsonc` caps score submissions at 12 per IP per minute. If your plan rejects it, delete that block; the Worker works without it.

## Launch

Drafts for Hacker News, Product Hunt, and Reddit are in `docs/launch.md`. Update the domain and review the copy before posting. Scheduled workflows handle content refreshes and daily posts, but the project still needs maintenance and replies to feedback.

## Licenses

Code: MIT. Real photos: credited to their Wikimedia Commons authors under the license shown. AI images: Rapidata datasets under CDLA-Permissive-2.0, or generated by this project.
