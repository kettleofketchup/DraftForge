"""Level-triggered queue for the `preview-env` label (spec §5.6).

`plan()` is a pure function: given the GitHub state of every open PR it
returns the label removals, label additions and `preview-queue` commit
statuses that bring the repo to the desired state. The I/O around it only
fetches that state and applies the plan (removals first, then additions).
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

LABEL = "preview-env"
OPT_OUT = "no-preview"
NO_BUILD_GRACE = timedelta(hours=2)
MAX_CAP = 10

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
CONFLICT = ("failure", "PR has merge conflicts; resolve them to build preview images")


def queued(position: int, total: int) -> tuple[str, str]:
    return ("success", f"Queued for a preview slot (position {position} of {total})")


@dataclass(frozen=True)
class PR:
    number: int
    author: str
    head_repo: str
    head_sha: str
    draft: bool
    labels: frozenset[str]
    created_at: datetime
    # (state, description) of the `preview-images` status on head_sha.
    images_status: tuple[str, str] | None
    # (created_at, state, description) of every `preview-queue` status on head_sha.
    queue_statuses: tuple[tuple[datetime, str, str], ...]
    # Latest `labeled` event for preview-env; None if unknown.
    grant_time: datetime | None
    # Both GHCR manifests for tag_for(number, head_sha) exist.
    manifests_exist: bool
    # From GET /pulls/{n}; None = not yet computed (unknown, not failed).
    mergeable: bool | None


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
    # Step 2: closed PRs still carrying the label lose it, and never count
    # as open even if the open list lags.
    closed = list(dict.fromkeys(closed_labelled))
    closed_set = set(closed)
    open_prs = [p for p in prs if p.number not in closed_set]

    def allowed(p: PR) -> bool:
        return (p.head_repo == base_repo and p.author in authors
                and OPT_OUT not in p.labels)

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

    # Step 3: eligibility.
    eligible = [p for p in open_prs if allowed(p)]
    ineligible = [p for p in open_prs if not allowed(p)]

    # Steps 4-5: holders; over cap, incumbents (earliest grant) win.
    holders = sorted((p for p in eligible if LABEL in p.labels), key=_grant_key)
    keep = holders[:cap]
    keep_nums = {p.number for p in keep}

    # Steps 6-7: waiters are built, non-failed eligible PRs without a slot.
    waiting = sorted(
        (p for p in eligible
         if p.number not in keep_nums and built(p) and not failed(p)),
        key=lambda p: (idle(p), p.created_at, p.number),
    )

    # Step 8: while waiters outnumber free slots, evict stale holders, oldest
    # head first, one per otherwise-unserved waiter.
    free = cap - len(keep)
    evictable = sorted(
        (p for p in keep if failed(p) or idle(p)),
        key=lambda p: (_first_seen(p) is None, _first_seen(p) or datetime.min,
                       *_grant_key(p)),
    )
    evicted = evictable[:max(0, min(len(evictable), len(waiting) - free))]
    evicted_nums = {p.number for p in evicted}
    keep = [p for p in keep if p.number not in evicted_nums]

    # Step 9: free slots go to the first waiters.
    free = cap - len(keep)
    promoted = waiting[:free]
    still_waiting = waiting[free:]
    desired = {p.number for p in keep} | {p.number for p in promoted}

    # Step 10: removals (closed first) precede additions.
    others = sorted(p.number for p in open_prs
                    if LABEL in p.labels and p.number not in desired)
    remove = closed + [n for n in others if n not in closed_set]
    add = [p.number for p in promoted if LABEL not in p.labels]

    # Step 11: statuses.
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
        if p.queue_statuses:
            wanted[p.number] = NOT_ELIGIBLE

    by_num = {p.number: p for p in open_prs}
    statuses = [
        (n, by_num[n].head_sha, state, desc)
        for n, (state, desc) in sorted(wanted.items())
        if _current_status(by_num[n]) != (state, desc)
    ]
    return Plan(remove=remove, add=add, statuses=statuses)
