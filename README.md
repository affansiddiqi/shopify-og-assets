# Shopify OG Instagram Autoposter

GitHub Actions publishing infrastructure for `@shopifyog`.

The queue is intentionally empty. Nothing publishes until an item is added to
`queue.json` with `status: "approved"` and a due `scheduled_at` timestamp.

Required encrypted repository secrets:

- `IG_PAGE_ACCESS_TOKEN`
- `IG_BUSINESS_ACCOUNT_ID`

Videos are placed in `videos/` and must remain publicly fetchable until Meta
finishes publishing them. Successfully published video files are removed from
the repository automatically.
