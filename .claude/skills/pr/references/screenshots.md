# Phase 4 — Before/after screenshots

Post one PR comment (never the PR body) that pairs a BEFORE and an AFTER image for
each visual change. Run this on every new PR, on a reused PR that has never had a
screenshot comment, and again whenever new commits change what the UI looks like.

Throughout: `<n>` is the PR number, `<wt>` the PR head worktree, `<base-wt>` the
before worktree, `<main>` = `/home/kettle/git_repos/draftforge` (the main checkout:
`git -C <main> worktree add/remove/fetch` is fine; never edit its files or run recipes in it).

## Every just command: the cd form

```bash
cd <wt> && just test::upd  # allow-cd
```

One Bash call, absolute path, `&& just ...`, and the `# allow-cd` marker. A subagent
shell resets its cwd between calls, so a bare `cd` followed by `just` in a second call
runs the recipe in the main checkout; `db::populate::fresh` there deletes the main
checkout's test DB. Use this form for every `just` call below, including populate,
migrate, slot and compose recipes.

## 1. Gate: does the diff have visual changes?

```bash
gh pr diff <n> --name-only | grep -E '^frontend/app/(components|routes|features)/|^frontend/app/app\.css$|tokens'
```

- **No match** → post the skip comment and go to Phase 5:

  ```bash
  gh pr comment <n> --body "No screenshots: this PR has no visual changes (no files under frontend/app/components, routes or features, app.css or design tokens)."
  ```

  Name what the diff does touch when it helps ("backend and CI only").
- **Match** → list each visual change: the page (URL path), the user role that sees it,
  and the states it affects. This list is the shot list; every entry gets a before and
  an after.

## 2. Shot list

For each change, decide:

| Item | Rule |
|---|---|
| Viewport | Desktop 1440×900. Add a 390×844 mobile shot when the layout differs at that width (stacked columns, sheets, overflow). |
| States | Capture every state the diff touches: hover, focus ring, open dialog/sheet/dropdown, empty, loading-finished, error and validation messages, the 409 conflict / confirm dialog. Mock a status with `page.route(...).fulfill({ status: 409, ... })` when real data cannot reach it. |
| Region | Crop to the changed region (`locator.screenshot()` or `page.screenshot({ clip })`), or draw a highlight box. Include enough surroundings to place it on the page. |
| Pairing | Before and after use the same URL, role, data, viewport and steps, and the same filename stem: `01-settings-dialog-before.png` / `01-settings-dialog-after.png`. |

A change that adds something new has no "before" state: shoot the same spot on the base
(where the new thing will appear) and caption it "not present before".

## 3. Stacks: before first, then after

Each worktree gets its own test stack slot; run one at a time.

### Before (merge-base)

```bash
git -C <wt> fetch origin
base=$(git -C <wt> merge-base origin/main HEAD)
git -C <main> worktree add --detach <main>/.worktrees/pr-<n>-base "$base"
ln -s <main>/.venv <main>/.worktrees/pr-<n>-base/.venv     # recipes need .venv
cp <main>/backend/.env <main>/.worktrees/pr-<n>-base/backend/.env
setfacl -R -m u:100999:rwX -m d:u:100999:rwX <main>/.worktrees/pr-<n>-base/frontend <main>/.worktrees/pr-<n>-base/backend
```

Then, in the base worktree (cd form for each):

```bash
cd <base-wt> && just test::upd  # allow-cd
cd <base-wt> && just test::slot  # allow-cd    -> prints DF_BASE_URL; use it, never assume https://localhost
cd <base-wt> && just db::populate::fresh  # allow-cd
cd <base-wt> && just test::compose restart backend nginx  # allow-cd
```

The restart is required: the backend holds the old SQLite file open, so without it the
API serves the deleted DB. Capture (section 4), then tear down and release, also when
the capture failed:

```bash
cd <base-wt> && just test::down && just test::slot-release  # allow-cd
```

### After (PR head)

Same four commands in `<wt>` (skip the worktree setup; add `.venv`, `backend/.env` and
`setfacl` only if missing), capture with the same script, then
`cd <wt> && just test::down && just test::slot-release  # allow-cd`.
Confirm with the read-only `just test::slots` (`test::slot` would allocate again).

### Is the stack serving the right code?

Before capturing, grep a string the PR adds inside the frontend container:
`cd <wt> && just test::compose exec frontend grep -rl '<new string>' /app/frontend/app  # allow-cd`
(adjust the path to the container's mount). Found in the after stack and absent in the
before stack means each stack serves its own tree.

### No free slot

`just test::upd` fails or `just test::slots` shows all slots taken: leave other
worktrees' slots alone (no `slot-reap`, `slot-claim` or `slot-release --slot N`) unless
the user tells you to free one. Pick one:

- Post `Screenshots pending: no free test stack slot. Will follow up.` and report it.
- Render the real component on a throwaway page outside the repo (e.g. a Vite page in
  `/tmp/pr-<n>-render/` importing the component from each tree) and say so in the
  comment's data note.

### Rootless podman errors

| Symptom | Fix |
|---|---|
| backend 500 "readonly database", or frontend `EACCES` crash loop | `setfacl -R -m u:100999:rwX -m d:u:100999:rwX <tree>/frontend <tree>/backend`, then `cd <tree> && just test::compose restart frontend backend nginx  # allow-cd` |
| container-owned `frontend/.react-router` or `frontend/node_modules/.vite` blocks a delete or rebuild | `podman unshare rm -rf <tree>/frontend/.react-router <tree>/frontend/node_modules/.vite` |

## 4. Capture (headless Playwright)

Headless only: a headed browser steals the user's focus. Write the script outside the
repo, e.g. `/tmp/pr-<n>-shots/capture.mjs`, and run it against each stack's URL. It
resolves Playwright from the PR worktree's `frontend/node_modules`
(`npm --prefix <wt>/frontend ci` once if that directory is missing).

```js
// node /tmp/pr-<n>-shots/capture.mjs <wt> <DF_BASE_URL> <before|after> /tmp/pr-<n>-shots
import { createRequire } from 'node:module';
import { mkdirSync } from 'node:fs';

const [wt, baseUrl, tag, out] = process.argv.slice(2);
const { chromium } = createRequire(`${wt}/frontend/package.json`)('@playwright/test');
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({ headless: true });
for (const [suffix, viewport] of [['', { width: 1440, height: 900 }], ['-mobile', { width: 390, height: 844 }]]) {
  const context = await browser.newContext({ viewport, ignoreHTTPSErrors: true });
  // Same test-only login endpoints as frontend/tests/playwright/fixtures/auth.ts
  const login = await context.request.post(`${baseUrl}/api/tests/login-admin/`);
  if (!login.ok()) throw new Error(`login ${login.status()}`);
  const page = await context.newPage();

  // Example steps; replace with the shot list (data-testid selectors from the component).
  await page.goto(`${baseUrl}/organizations/7`, { waitUntil: 'networkidle' });
  await page.getByTestId('event-settings-button').click();
  const dialog = page.getByRole('dialog');
  await dialog.waitFor();
  await dialog.screenshot({ path: `${out}/01-settings-dialog${suffix}-${tag}.png` });

  await context.close();
}
await browser.close();
```

Replace the page steps with the shot list. Other roles: `login-as/` with
`{ data: { user_pk } }` (users and PKs in the `testing` skill's data table; endpoint
list in `fixtures/auth.ts`). Drop the mobile pass when the layout does not differ.

## 5. Look at every PNG

Open each file with the Read tool before posting. Retake any shot that is blank, shows a
spinner or skeleton, a login page, an error boundary, a half-finished animation, or cuts
off the changed region. Check the before/after pair shows the same place. Real people's
names or partner organisation names in a shot: retake with test data.

## 6. Publish the images

GitHub has no CLI upload for comment attachments, so the PNGs live on an orphan branch
`pr-assets/<n>` (the repo is public, so raw URLs render).

```bash
git -C <main> fetch origin
git -C <main> worktree add --detach /tmp/pr-assets-<n>
if git -C <main> ls-remote --exit-code origin "refs/heads/pr-assets/<n>" >/dev/null; then
  git -C /tmp/pr-assets-<n> switch -c pr-assets/<n> --track origin/pr-assets/<n>
else
  git -C /tmp/pr-assets-<n> switch --orphan pr-assets/<n>
fi
cp /tmp/pr-<n>-shots/*.png /tmp/pr-assets-<n>/
git -C /tmp/pr-assets-<n> add -- '*.png'
PRE_COMMIT_ALLOW_NO_CONFIG=1 git -C /tmp/pr-assets-<n> commit -m "Screenshots for PR #<n>"
git -C /tmp/pr-assets-<n> push -u origin pr-assets/<n>
git -C <main> worktree remove --force /tmp/pr-assets-<n>
```

An existing branch gets a new commit on top; plain `git push` only. On a later round,
give files a new stem (`-r2`) so earlier comments keep their images.

## 7. Post the comment

```bash
gh repo view --json nameWithOwner -q .nameWithOwner     # -> <owner>/<repo>
gh pr comment <n> --body-file /tmp/pr-<n>-shots/comment.md
```

`comment.md` is a heading, one section per change, and a data note:

```markdown
## Screenshots

### Event settings dialog: sidebar with search
| Before | After |
|---|---|
| ![before](https://raw.githubusercontent.com/<owner>/<repo>/refs/heads/pr-assets/<n>/01-settings-dialog-before.png) | ![after](https://raw.githubusercontent.com/<owner>/<repo>/refs/heads/pr-assets/<n>/01-settings-dialog-after.png) |
| Flat list of settings | Grouped sidebar; search filters the groups |

Mobile (390 px):
| Before | After |
|---|---|
| <img width="320" src="https://raw.githubusercontent.com/<owner>/<repo>/refs/heads/pr-assets/<n>/01-settings-dialog-mobile-before.png"> | <img width="320" src="https://raw.githubusercontent.com/<owner>/<repo>/refs/heads/pr-assets/<n>/01-settings-dialog-mobile-after.png"> |

Data: test stack after `just db::populate::fresh`, logged in as the test admin; before = merge-base `<short sha>`, after = `<head short sha>`. The 409 state is a mocked response.
```

The comment is written as the user's own: no AI or tool attribution, no partner
organisation names. New visual commits later get a fresh comment (with `-r2` files);
old comments stay as they are.

## 8. Clean up

- Stacks down and slots released in both trees (section 3); `just test::slots` shows neither.
- `git -C <main> worktree remove --force --force <main>/.worktrees/pr-<n>-base`; if
  container-owned files block it, `podman unshare rm -rf <base-wt>` then
  `git -C <main> worktree prune`.
- `git -C <wt> status --short` shows no screenshots or scripts in the PR tree.
