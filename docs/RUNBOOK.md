# Runbook

## Static snapshot of the public demo

The public demo can be served as static files: the web app plus every response it needs, saved from the built demo database. No server, no database, no sign-in. Decided by Bryan on 2026-11-15 (Backlog bl_116); how it works is `docs/DECISIONS.md` 96. It is served on Cloudflare Pages, project `account-desk-demo`, with noindex. 2026-11-27: it is the live demo the README links (since 8dda520, 2026-11-18). The Render demo is unchanged and stays the full one.

### What the snapshot holds

The demo it reads is the one the hosted image holds: the shared world's 3,000 accounts over 91 days (`WORLD=world`, the `Dockerfile` default), the same database `python -m outbound demo` builds. Not the 90-day generator, and not the large 5,000-account databases the load tests use.

- Every page in the navigation, for each of the 8 people the demo can act as. The sidebar's "Acting as" works: an SDR sees their own Today, In flight and Replies; the manager and GTM see the money (Results, Plays) and the pages only they have (Inboxes, Vendors and costs, Health, Settings, suggested plays). A rep gets the server's own "Your role cannot do this." where the server says it.
- Every record a side sheet can open: accounts, people, emails, replies, tasks, meetings, plays (with their accounts and where each came from) and suggested plays.
- The Accounts page: every page of Fit our profile, In a play, Rising this week and All, and each person's Mine. Its search runs in the browser over every saved account, in the server's order.
- The check on an email's text as it opens (the problems the send gate would list) and each play's preview.

### What degrades, and how

- Every change (approve, reject, send a reply, log a call, kill switch, users, the profile, imports, rules, "Move a day ahead") gets the public demo's own refusal: "Not available in the public demo." Nothing is saved, and nothing moves: the clock is frozen at the build's.
- Editing an email or a reply and checking the new text, refining a reply, and a play preview for changed settings are not in the snapshot: the check shows nothing new (as when the server is slow) and the preview says it is not in the snapshot.
- A page of accounts that the server would not have shown, or a path no screen asks for, answers "This view is not in the snapshot. Run the demo yourself to see it."
- Pages that only exist beside other desks (links to CRM Desk, Events Desk, Market Desk) are off: the snapshot calls no other service.
- The unsubscribe pages (`/u/...`) are server pages and are not part of the snapshot.
- The snapshot is as old as its build. The note at the top of every page says when it was taken.

### Build

```bash
WORLD=world PYTHONPATH=src .venv/bin/python -m outbound demo   # no day count: the world's 91 days; DATABASE_URL names the database
make snapshot      # writes .snapshot/; DATABASE_URL names the demo database
```

`make demo` is not the same demo (it builds the 90-day generator), so build the world demo with the command above, then run `make snapshot` against the same database. The build takes 15 to 60 minutes depending on the machine. `scripts/build_static_snapshot.py` builds the web app, runs the API inside the script's own process (FastAPI's test client, no port) against the demo database with `PUBLIC_DEMO=1`, and reads it the way the screens do, as each person. It refuses a `sim_` or Neon database. The crawl sends only GETs and the two reads that take a body, and the database's fingerprint (row count and newest row version of every table) is compared before and after, so the build stops if the crawl changed anything. The API's own start-up comes before the first fingerprint. It also stops when a path the screens read (parsed from `web/src`) has no saved answer, when the bundle is over 60 MB, or over 19,000 files (Cloudflare Pages takes 20,000 files and 25 MB a file).

Answers are saved once when everyone gets the same one, and per kind of person or per person when they differ (the key's scope: `*`, `r:sdr`, `r:mgr`, `u:<id>`). The tests check that the shared ones really are the same for every person.

The bundle: `index.html` with `<meta name="robots" content="noindex,nofollow">` and `snapshot-shim.js` loaded first; `_snapshot/` holds the saved answers as gzip shards (up to 4,096) keyed by the first 3 hex digits of each request's SHA-1 (method, path, sorted query, body with sorted keys), plus `accounts.json.gz` (the search) and `config.json.gz` (who the demo can act as); `_headers` sends `X-Robots-Tag: noindex, nofollow` and the app's own security headers on every path; `robots.txt` disallows everything; `snapshot-manifest.json` lists every saved request. Size and timing of the last build are in `PROJECT-STATUS.md`.

`tests/test_static_snapshot.py` checks that every path the screens read has a saved answer, that the crawl changes nothing, that what is saved once is the same for everyone, that a rep gets no money, that the shim and the build compute the same key and the shim picks each person's answer, that every change gets the refusal, and that the bundle is noindex.

### Deploy

GitHub Actions, `.github/workflows/static-snapshot.yml`: on a push to `main` that touches `web/`, the snapshot script or the workflow, and by hand (Actions, static snapshot, Run workflow). It builds the demo on a throwaway Postgres (15 to 60 minutes), builds the snapshot, keeps it as an artifact for 30 days (`account-desk-snapshot-<commit>`), and deploys to Pages only when the repository secrets `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` are set. Without them the run passes and deploys nothing. Both are set (2026-11-18), so a qualifying push deploys; the last deploy was run 45962320513 at d1be7b7 on 2026-11-27. 2026-11-27: runs up to then kept no artifact, because `.snapshot` is a hidden folder that `upload-artifact` skipped; the step now sets `include-hidden-files: true`. The repository is public, so its runs cost no Actions minutes.

From a laptop, with the token from Infisical (the Infisical project, prod, root path; never printed):

```bash
infisical run --projectId <project id> --env prod --recursive -- sh -c 'env -i PATH="$PATH" HOME="$HOME" CLOUDFLARE_API_TOKEN="$CLOUDFLARE_API_TOKEN" CLOUDFLARE_ACCOUNT_ID="$CLOUDFLARE_ACCOUNT_ID" npx --yes wrangler@4.156.1 pages deploy .snapshot --project-name account-desk-demo --branch main'
```

### Roll back

Each deploy is kept. Either:

- List the deployments (`npx wrangler@4.156.1 pages deployment list --project-name account-desk-demo`, same environment as above) and roll production back to an earlier one: in the Cloudflare dashboard (Workers and Pages, account-desk-demo, Deployments, the deployment's menu, Rollback to this deployment), or through the API, `POST /accounts/<account>/pages/projects/account-desk-demo/deployments/<deployment id>/rollback` with the token. Tested on 2026-11-17: a rollback to the previous deployment and back again, each serving within seconds.
- Or download an earlier run's artifact from GitHub Actions and deploy that folder with the command above (only runs after 2026-11-27 have one).

To take the snapshot down entirely, delete the Pages project in the dashboard (only on Bryan's word).
