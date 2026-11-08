"""Level-triggered queue for the `preview-env` label.

`plan()` is a pure function: given the GitHub state of every open PR it
returns the label removals, label additions and `preview-queue` commit
statuses that bring the repo to the desired state. The I/O around it only
fetches that state and applies the plan (removals first, then additions).

`main` fetches everything first (all pages of every list, every GHCR check),
so an API error anywhere exits non-zero before a single write.

Run by .github/workflows/preview-queue.yml as `python3 -I scripts/preview_queue.py`
with GH_TOKEN, GH_REPO, CAP, PREVIEW_AUTHORS, PREVIEW_IDLE_DAYS,
PREVIEW_REQUIRE_VERIFIED and CLOSED_PR.

A PR is eligible only if every commit on its head was authored and committed
by a PREVIEW_AUTHORS login (GitHub's own web-flow committer is accepted for
commits made in the web UI). GitHub maps those logins from the commit e-mail,
which anyone can set, so the check only stops a collaborator from pushing to
an allowlisted author's branch by accident or in plain sight; with
PREVIEW_REQUIRE_VERIFIED=true every commit must also carry a verified
signature, which makes the check hold.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone

LABEL = "preview-env"
OPT_OUT = "no-preview"
NO_BUILD_GRACE = timedelta(hours=2)
# Raising the ceiling is a reviewed code change, not a repo-variable edit: the
# deploying cluster budgets capacity for this many previews.
MAX_CAP = 3

# PREVIEW_AUTHORS entries are compared exactly and case-sensitively with
# `user.login`, so they must use the canonical case GitHub returns. The
# preview-images workflow's `contains()` is case-insensitive; a mis-cased entry
# would build images there but never be admitted here.
LOGIN_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
UINT_RE = re.compile(r"^[0-9]+$")

HELD = ("success", "Preview slot held")
WAITING_IMAGES = ("pending", "Waiting for preview images")
IMAGES_FAILED = ("failure", "Preview images failed for this commit")
RELEASED = ("success", "Preview slot released (idle or failed build); queued again")
NO_BUILD = (
    "success",
    "No preview build for this commit; push a commit (or close and reopen) to build",
)
NOT_ELIGIBLE = ("success", "Not eligible for a preview")
OUTSIDE_COMMITS = (
    "success",
    "No preview: a commit on this head is not by a preview author",
)
# GitHub's committer for commits made in the web UI (merges, suggestions).
WEB_FLOW = "web-flow"
# GET /pulls/{n}/commits returns at most this many; a longer PR cannot be checked.
MAX_PR_COMMITS = 250
CONFLICT = ("failure", "PR has merge conflicts; resolve them to build preview images")


def queued(position: int, total: int) -> tuple[str, str]:
    return ("success", f"Queued for a preview slot (position {position} of {total})")


@dataclass(frozen=True)
class PR:
    number: int
    author: str
    head_repo: str
    head_sha: str
    labels: frozenset[str]
    created_at: datetime
    # (state, description) of the latest `preview-images` status on head_sha
    # whose description is this PR's tag. Statuses attach to a SHA repo-wide, so
    # another PR on the same head posts its own tag there.
    images_status: tuple[str, str] | None
    # (created_at, state, description) of every queue_context(number) status on head_sha.
    queue_statuses: tuple[tuple[datetime, str, str], ...]
    # Latest `labeled` event for preview-env; None if unknown.
    grant_time: datetime | None
    # Both GHCR manifests for tag_for(number, head_sha) exist.
    manifests_exist: bool
    # From GET /pulls/{n}; None = not yet computed (unknown, not failed).
    mergeable: bool | None
    # A head commit not authored and committed by an allowlisted login (see
    # commits_outside). None = not checked, which counts as outside.
    outside_commits: bool | None = None


@dataclass(frozen=True)
class Plan:
    remove: list[int]
    add: list[int]
    # (pr, sha, state, description), only statuses that differ from the latest.
    statuses: list[tuple[int, str, str, str]]


def tag_for(n: int, sha: str) -> str:
    return f"pr-{n}-{sha[:7]}"


def parse_config(cap: str, authors: str, idle_days: str) -> tuple[int, frozenset[str], int]:
    """Validate PREVIEW_CAP, PREVIEW_AUTHORS and PREVIEW_IDLE_DAYS.

    Raises ValueError on anything malformed, before the caller writes anything.
    """
    if not UINT_RE.fullmatch(cap) or not 0 <= int(cap) <= MAX_CAP:
        raise ValueError(f"PREVIEW_CAP must be an integer 0-{MAX_CAP}, got {cap!r}")
    entries = authors.split(",")
    for entry in entries:
        if not LOGIN_RE.fullmatch(entry):
            raise ValueError(
                "PREVIEW_AUTHORS must be comma-separated GitHub logins in canonical "
                f"case, no whitespace or empty entries; bad entry {entry!r}"
            )
    if not UINT_RE.fullmatch(idle_days) or not 1 <= int(idle_days) <= 365:
        raise ValueError(f"PREVIEW_IDLE_DAYS must be an integer 1-365, got {idle_days!r}")
    return int(cap), frozenset(entries), int(idle_days)


def parse_require_verified(value: str) -> bool:
    """PREVIEW_REQUIRE_VERIFIED: empty or "false" is off, "true" is on."""
    if value in ("", "false"):
        return False
    if value == "true":
        return True
    raise ValueError(f"PREVIEW_REQUIRE_VERIFIED must be true or false, got {value!r}")


def commits_outside(commits: list[tuple[str, str, bool]], authors: frozenset[str],
                    require_verified: bool) -> bool:
    """True unless every (author login, committer login, verified) commit is by
    an allowlisted login. An empty or possibly truncated list counts as outside."""
    if not commits or len(commits) >= MAX_PR_COMMITS:
        return True
    for author, committer, verified in commits:
        if author not in authors:
            return True
        if committer not in authors and committer != WEB_FLOW:
            return True
        if require_verified and not verified:
            return True
    return False


def _first_seen(pr: PR) -> datetime | None:
    """Earliest preview-queue status on the head: roughly when it was pushed."""
    return min((t for t, _s, _d in pr.queue_statuses), default=None)


def _current_status(pr: PR) -> tuple[str, str] | None:
    if not pr.queue_statuses:
        return None
    _t, state, desc = max(pr.queue_statuses, key=lambda s: s[0])
    return (state, desc)


def _grant_key(pr: PR):
    # Unknown grant time sorts as the newest grant.
    return (pr.grant_time is None, pr.grant_time or datetime.min, pr.number)


def plan(prs: list[PR], closed_labelled: list[int], now: datetime, cap: int,
         authors: frozenset[str], idle_days: int, base_repo: str) -> Plan:
    # Closed PRs still carrying the label lose it, and never count as open
    # even if the open list lags.
    closed = list(dict.fromkeys(closed_labelled))
    closed_set = set(closed)
    open_prs = [p for p in prs if p.number not in closed_set]

    def by_author(p: PR) -> bool:
        return (p.head_repo == base_repo and p.author in authors
                and OPT_OUT not in p.labels)

    def allowed(p: PR) -> bool:
        return by_author(p) and p.outside_commits is False

    def built(p: PR) -> bool:
        tag = tag_for(p.number, p.head_sha)
        return p.images_status == ("success", tag) and p.manifests_exist

    def images_failed(p: PR) -> bool:
        return p.images_status == ("failure", tag_for(p.number, p.head_sha))

    def failed(p: PR) -> bool:
        return images_failed(p) or p.mergeable is False

    def idle(p: PR) -> bool:
        seen = _first_seen(p)
        return seen is not None and now - seen > timedelta(days=idle_days)

    def no_build(p: PR) -> bool:
        seen = _first_seen(p)
        return p.images_status is None and seen is not None and now - seen > NO_BUILD_GRACE

    # Eligibility.
    eligible = [p for p in open_prs if allowed(p)]
    ineligible = [p for p in open_prs if not allowed(p)]

    # Holders; over cap, incumbents (earliest grant) win.
    holders = sorted((p for p in eligible if LABEL in p.labels), key=_grant_key)
    keep = holders[:cap]
    keep_nums = {p.number for p in keep}

    # Waiters are built, non-failed eligible PRs without a slot.
    waiting = sorted(
        (p for p in eligible
         if p.number not in keep_nums and built(p) and not failed(p)),
        key=lambda p: (idle(p), p.created_at, p.number),
    )

    # While waiters outnumber free slots, evict stale holders, one per
    # otherwise-unserved waiter: failed holders first, then idle ones, oldest
    # head first within each. Free and freed slots go to non-idle waiters
    # first (waiter order), so an idle holder is evicted only for a non-idle
    # waiter that a free or failed slot does not already serve. Otherwise an
    # idle waiter would take an idle holder's slot, the evicted PR would be
    # the idle waiter on the next run, and the two would trade the slot every
    # run; and an idle holder evicted while a failed holder stays would take
    # the failed holder's slot back on the next run.
    free = cap - len(keep)
    unserved = max(0, len(waiting) - free)
    unserved_active = max(0, sum(1 for p in waiting if not idle(p)) - free)
    by_age = sorted(
        keep,
        key=lambda p: (_first_seen(p) is None, _first_seen(p) or datetime.min,
                       *_grant_key(p)),
    )
    evicted = [p for p in by_age if failed(p)][:unserved]
    room = max(0, unserved_active - len(evicted))
    evicted += [p for p in by_age if idle(p) and not failed(p)][:room]
    evicted_nums = {p.number for p in evicted}
    keep = [p for p in keep if p.number not in evicted_nums]

    # Free slots go to the first waiters.
    free = cap - len(keep)
    promoted = waiting[:free]
    still_waiting = waiting[free:]
    desired = {p.number for p in keep} | {p.number for p in promoted}

    # Removals (closed first) precede additions.
    others = sorted(p.number for p in open_prs
                    if LABEL in p.labels and p.number not in desired)
    remove = closed + [n for n in others if n not in closed_set]
    add = [p.number for p in promoted if LABEL not in p.labels]

    # Statuses.
    position = {p.number: i for i, p in enumerate(still_waiting, start=1)}
    wanted: dict[int, tuple[str, str]] = {}
    for p in eligible:
        if p.mergeable is False:
            wanted[p.number] = CONFLICT
        elif p.number in evicted_nums:
            wanted[p.number] = RELEASED
        elif images_failed(p):
            wanted[p.number] = IMAGES_FAILED
        elif p.number in desired:
            wanted[p.number] = HELD
        elif p.number in position:
            wanted[p.number] = queued(position[p.number], len(still_waiting))
        elif no_build(p):
            wanted[p.number] = NO_BUILD
        else:
            wanted[p.number] = WAITING_IMAGES
    for p in ineligible:
        if by_author(p):
            wanted[p.number] = OUTSIDE_COMMITS
        elif p.queue_statuses:
            wanted[p.number] = NOT_ELIGIBLE

    by_num = {p.number: p for p in open_prs}
    statuses = [
        (n, by_num[n].head_sha, state, desc)
        for n, (state, desc) in sorted(wanted.items())
        if _current_status(by_num[n]) != (state, desc)
    ]
    return Plan(remove=remove, add=add, statuses=statuses)


# --- I/O ---

API = "https://api.github.com"
GHCR = "https://ghcr.io"
QUEUE_CONTEXT = "preview-queue"


def queue_context(n: int) -> str:
    """Per-PR status context: two PRs on one head SHA must not share statuses."""
    return f"{QUEUE_CONTEXT}/pr-{n}"
IMAGES_CONTEXT = "preview-images"
PREVIEW_IMAGES = (
    "kettleofketchup/draftforge-preview/backend",
    "kettleofketchup/draftforge-preview/frontend",
)
MANIFEST_TYPES = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
)
TIMEOUT = 30

# (status, headers, body). HTTP errors come back as a status, never raised.
Opener = Callable[[urllib.request.Request], tuple[int, Mapping[str, str], bytes]]


def default_opener(req: urllib.request.Request) -> tuple[int, Mapping[str, str], bytes]:
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as exc:
        headers = dict(exc.headers.items()) if exc.headers else {}
        return exc.code, headers, exc.read()


class GitHubError(Exception):
    pass


class RegistryError(Exception):
    pass


def _header(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return ""


LINK_NEXT_RE = re.compile(r'<([^>]+)>\s*;\s*rel="next"')


def _next_link(headers: Mapping[str, str]) -> str | None:
    match = LINK_NEXT_RE.search(_header(headers, "Link"))
    return match.group(1) if match else None


def _with_per_page(url: str) -> str:
    """`url` with per_page=100; a URL that already has it is returned unchanged."""
    parts = urllib.parse.urlsplit(url)
    pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    if [v for k, v in pairs if k == "per_page"] == ["100"]:
        return url
    query = [(k, v) for k, v in pairs if k != "per_page"]
    query.append(("per_page", "100"))
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class GitHub:
    def __init__(self, token: str, repo: str, opener: Opener = default_opener):
        self.token = token
        self.repo = repo
        self.opener = opener

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "GitHub":
        token, repo = env.get("GH_TOKEN", ""), env.get("GH_REPO", "")
        if not token or not repo:
            raise GitHubError("GH_TOKEN and GH_REPO must be set")
        return cls(token, repo)

    def _send(self, method: str, url: str, body: dict | None = None):
        if not url.startswith(API + "/"):
            raise GitHubError(f"refusing to send the token outside {API}: {url}")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "draftforge-preview-queue")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            return self.opener(req)
        except OSError as exc:
            raise GitHubError(f"{method} {url}: {exc}") from exc

    def _url(self, path: str, params: Mapping[str, str] = {}) -> str:
        url = f"{API}/{path}"
        return f"{url}?{urllib.parse.urlencode(dict(params))}" if params else url

    @staticmethod
    def _json(method: str, url: str, status: int, body: bytes):
        if not 200 <= status < 300:
            raise GitHubError(f"{method} {url}: HTTP {status}: {body[:200]!r}")
        try:
            return json.loads(body)
        except ValueError as exc:
            raise GitHubError(f"{method} {url}: invalid JSON: {exc}") from exc

    def _get_all(self, path: str, params: Mapping[str, str] = {},
                 items_key: str | None = None) -> list[dict]:
        """Every item of a list endpoint, following `Link: rel="next"` to the end."""
        url: str | None = _with_per_page(self._url(path, params))
        items: list[dict] = []
        while url:
            status, headers, body = self._send("GET", url)
            data = self._json("GET", url, status, body)
            if items_key:
                page = data.get(items_key) if isinstance(data, dict) else None
            else:
                page = data
            if not isinstance(page, list):
                raise GitHubError(f"GET {url}: expected a list, got {type(page).__name__}")
            items.extend(page)
            nxt = _next_link(headers)
            url = _with_per_page(nxt) if nxt else None
        return items

    def _get_one(self, path: str) -> dict:
        url = self._url(path)
        status, _headers, body = self._send("GET", url)
        return self._json("GET", url, status, body)

    def _write(self, method: str, path: str, body: dict | None = None,
               ok_404: bool = False) -> None:
        url = self._url(path)
        status, _headers, data = self._send(method, url, body)
        if ok_404 and status == 404:
            return
        if not 200 <= status < 300:
            raise GitHubError(f"{method} {url}: HTTP {status}: {data[:200]!r}")

    def _pr(self, raw: dict) -> PR:
        n = raw["number"]
        head = raw["head"]["sha"]
        labels = frozenset(label["name"] for label in raw.get("labels", []))
        grant = None
        if LABEL in labels:
            events = self._get_all(f"repos/{self.repo}/issues/{n}/events")
            grants = [_time(e["created_at"]) for e in events
                      if e.get("event") == "labeled"
                      and (e.get("label") or {}).get("name") == LABEL]
            grant = max(grants, default=None)
        statuses = self._get_all(f"repos/{self.repo}/commits/{head}/statuses")
        tag = tag_for(n, head)
        images = [s for s in statuses if s.get("context") == IMAGES_CONTEXT
                  and (s.get("description") or "") == tag]
        # Newest first from the API; max() keeps the first of equal timestamps.
        latest = max(images, key=lambda s: _time(s["created_at"]), default=None)
        queue = tuple((_time(s["created_at"]), s["state"], s.get("description") or "")
                      for s in statuses if s.get("context") == queue_context(n))
        detail = self._get_one(f"repos/{self.repo}/pulls/{n}")
        head_repo = (raw["head"].get("repo") or {}).get("full_name", "")
        return PR(
            number=n,
            author=raw["user"]["login"],
            head_repo=head_repo,
            head_sha=head,
            labels=labels,
            created_at=_time(raw["created_at"]),
            images_status=(latest["state"], latest.get("description") or "") if latest else None,
            queue_statuses=queue,
            grant_time=grant,
            manifests_exist=False,  # checked by main, only for heads that need it
            mergeable=detail.get("mergeable"),
        )

    def pr_commits(self, n: int) -> list[tuple[str, str, bool]]:
        """(author login, committer login, signature verified) per head commit.
        A commit whose e-mail maps to no GitHub user has an empty login."""
        out = []
        for c in self._get_all(f"repos/{self.repo}/pulls/{n}/commits"):
            verification = (c.get("commit") or {}).get("verification") or {}
            out.append(((c.get("author") or {}).get("login") or "",
                        (c.get("committer") or {}).get("login") or "",
                        verification.get("verified") is True))
        return out

    def open_prs(self) -> list[PR]:
        pulls = self._get_all(f"repos/{self.repo}/pulls", {"state": "open"})
        return [self._pr(raw) for raw in pulls]

    def closed_labelled(self) -> list[int]:
        query = f"repo:{self.repo} is:pr is:closed label:{LABEL}"
        items = self._get_all("search/issues", {"q": query}, items_key="items")
        return [item["number"] for item in items]

    def remove_label(self, n: int) -> None:
        # 404: the label is already gone.
        self._write("DELETE", f"repos/{self.repo}/issues/{n}/labels/{LABEL}", ok_404=True)

    def add_label(self, n: int) -> None:
        self._write("POST", f"repos/{self.repo}/issues/{n}/labels", {"labels": [LABEL]})

    def set_status(self, n: int, sha: str, state: str, desc: str) -> None:
        self._write("POST", f"repos/{self.repo}/statuses/{sha}",
                    {"state": state, "description": desc, "context": queue_context(n)})


def manifest_exists(image: str, tag: str, opener: Opener = default_opener) -> bool:
    """Anonymous GHCR check that `<image>:<tag>` exists (the packages are public)."""
    token_url = f"{GHCR}/token?scope=repository:{image}:pull"
    try:
        status, _h, body = opener(urllib.request.Request(token_url, method="GET"))
    except OSError as exc:
        raise RegistryError(f"GET {token_url}: {exc}") from exc
    if status != 200:
        raise RegistryError(f"GET {token_url}: HTTP {status}")
    try:
        token = json.loads(body)["token"]
    except (ValueError, KeyError, TypeError) as exc:
        raise RegistryError(f"GET {token_url}: no token in response") from exc
    url = f"{GHCR}/v2/{image}/manifests/{tag}"
    req = urllib.request.Request(url, method="HEAD")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", ", ".join(MANIFEST_TYPES))
    try:
        status, _h, _body = opener(req)
    except OSError as exc:
        raise RegistryError(f"HEAD {url}: {exc}") from exc
    if status == 200:
        return True
    if status == 404:
        return False
    raise RegistryError(f"HEAD {url}: HTTP {status}")


def _log(msg: str) -> None:
    print(f"preview-queue: {msg}", file=sys.stderr)


def main(env: Mapping[str, str], gh: GitHub, manifest_exists=manifest_exists) -> int:
    try:
        cap, authors, idle_days = parse_config(
            env.get("CAP", ""), env.get("PREVIEW_AUTHORS", ""), env.get("PREVIEW_IDLE_DAYS", ""))
        require_verified = parse_require_verified(env.get("PREVIEW_REQUIRE_VERIFIED", ""))
        closed_pr = env.get("CLOSED_PR", "")
        if closed_pr and not UINT_RE.fullmatch(closed_pr):
            raise ValueError(f"CLOSED_PR must be empty or a PR number, got {closed_pr!r}")
    except ValueError as exc:
        _log(f"config error, nothing written: {exc}")
        return 2

    # Fetch everything before the first write.
    try:
        prs = [p for p in gh.open_prs() if str(p.number) != closed_pr]
        # The search index lags; the PR that just closed loses its label now.
        closed = list(dict.fromkeys(gh.closed_labelled() + ([int(closed_pr)] if closed_pr else [])))
        checked = []
        for p in prs:
            tag = tag_for(p.number, p.head_sha)
            exists = (p.images_status == ("success", tag)
                      and all(manifest_exists(image, tag) for image in PREVIEW_IMAGES))
            outside = None
            if p.head_repo == gh.repo and p.author in authors:
                outside = commits_outside(gh.pr_commits(p.number), authors, require_verified)
            checked.append(replace(p, manifests_exist=exists, outside_commits=outside))
    except (GitHubError, RegistryError) as exc:
        _log(f"fetch failed, nothing written: {exc}")
        return 1

    result = plan(checked, closed, datetime.now(timezone.utc), cap, authors, idle_days,
                  gh.repo)
    print(f"remove={result.remove} add={result.add} statuses={len(result.statuses)}")
    try:
        for n in result.remove:
            gh.remove_label(n)
        for n in result.add:
            gh.add_label(n)
        for n, sha, state, desc in result.statuses:
            print(f"#{n} {sha[:7]}: {state} {desc}")
            gh.set_status(n, sha, state, desc)
    except GitHubError as exc:
        _log(f"write failed; the next run reconciles: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(os.environ, GitHub.from_env()))
