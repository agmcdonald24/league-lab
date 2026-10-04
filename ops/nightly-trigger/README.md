# The nightly's trigger (Cloudflare Worker)

GitHub's `schedule` is best-effort: every scheduled nightly from 2026-09-30 to 2026-10-03 started 3.5–6 hours late and
the 09:07 ET backup never ran as its own run. This Worker starts the workflow by `workflow_dispatch` at **07:37
America/New_York** every day and re-checks at 09:37 and 11:37 (dispatching only when nothing succeeded or is running
today). The workflow's own schedule stays as the last resort; its `gate` job never skips a dispatched run and skips a
late scheduled one once a run has succeeded that day. Full notes: `docs/HOSTING.md` § "The trigger".

Set-up (once):

1. GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate: repository
   access = only `league-lab`; repository permissions = **Actions: Read and write**; expiry = 1 year (note the date in
   HOSTING). Copy the token.
2. Cloudflare → Workers & Pages → Create → Worker → name `isuckatfantasy-nightly-trigger` → paste `src/index.js` →
   Deploy. Settings → Triggers → Cron Triggers → `37 * * * *`. Settings → Variables and Secrets: the five variables
   from `wrangler.jsonc` (plain), and **`GITHUB_TOKEN` as a Secret** (the token from step 1).
   Or, with wrangler: `npm i -g wrangler && wrangler login`, then from this directory `wrangler secret put
   GITHUB_TOKEN` and `wrangler deploy`.
3. Open the Worker's URL: it prints what it does and today's runs. The next 07:37 ET shows a `workflow_dispatch` run
   in GitHub Actions within a minute.

Rotation: a new token → the same secret. Rollback: delete the Worker (GitHub's schedule carries on, late).

**The last dispatch on the status page (Wave I-H, IH-1; optional).** A Worker keeps nothing between runs without a
binding. Bind a Workers KV namespace (free) as `STATE` and the Worker records each dispatch — success, or the HTTP error
(401: the token expired or lacks "Actions: write"; 404: the repository or workflow name; 422: the branch) and when —
and its URL prints `last dispatch: ok (HTTP 204) at Oct 5, 2026, 7:37 AM ET — the morning run`, or `FAILED at …`.
Cloudflare → Workers & Pages → **KV** → Create namespace `isuckatfantasy-nightly-state`; the Worker → Settings →
**Bindings** → Add → KV namespace → variable name `STATE`, that namespace → Deploy. Or in `wrangler.jsonc`:
`"kv_namespaces": [{ "binding": "STATE", "id": "<the namespace id>" }]`. Without it the Worker works as before and
the page says the dispatch is not recorded. Offline checks (GitHub mocked, KV faked): `node ops/nightly-trigger/test.mjs`.
