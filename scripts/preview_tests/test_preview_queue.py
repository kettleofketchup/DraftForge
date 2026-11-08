"""Tests for the preview queue.

The planner cases build `PR` records by hand and call `plan()` directly. The
I/O cases drive the real `GitHub` client and `manifest_exists` through a
canned transport, and `main` through a fake client that records writes.
"""
import contextlib
import io
import json
import unittest
import urllib.parse
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from scripts import preview_queue
from scripts.preview_queue import (PR, GitHub, GitHubError, Plan, RegistryError, main,
                                   manifest_exists, parse_config, plan, tag_for)

BASE = "kettleofketchup/DraftForge"
OWNER = "kettleofketchup"
AUTHORS = frozenset({OWNER})
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
IDLE_DAYS = 7

HELD = ("success", "Preview slot held")
WAITING_IMAGES = ("pending", "Waiting for preview images")
IMAGES_FAILED = ("failure", "Preview images failed for this commit")
RELEASED = ("success", "Preview slot released (idle or failed build); queued again")
NO_BUILD = (
    "success",
    "No preview build for this commit; push a commit (or close and reopen) to build",
)
NOT_ELIGIBLE = ("success", "Not eligible for a preview")
OUTSIDE = ("success", "No preview: a commit on this head is not by a preview author")
CONFLICT = ("failure", "PR has merge conflicts; resolve them to build preview images")


def queued(k, m):
    return ("success", f"Queued for a preview slot (position {k} of {m})")


def sha(n, rev=0):
    """Head SHA of PR n; `rev` changes the first 7 chars (the tag part)."""
    return f"{n:04d}{rev:03d}" + "a" * 33


def mk(n, *, built=True, labelled=False, author=OWNER, head_repo=BASE, rev=0,
       labels=(), created=None, images=None, manifests=None,
       queue=(), grant=None, mergeable=True, outside=False):
    """One open PR. `built=True` means a success status with this PR's tag and
    both manifests present; `images`/`manifests` override that explicitly."""
    head = sha(n, rev)
    if images is None and built:
        images = ("success", tag_for(n, head))
    if manifests is None:
        manifests = built
    lbls = set(labels)
    if labelled:
        lbls.add("preview-env")
        if grant is None:
            grant = NOW - timedelta(days=1)
    return PR(
        number=n,
        author=author,
        head_repo=head_repo,
        head_sha=head,
        labels=frozenset(lbls),
        created_at=created or (NOW - timedelta(days=30) + timedelta(hours=n)),
        images_status=images,
        queue_statuses=tuple(queue),
        grant_time=grant,
        manifests_exist=manifests,
        mergeable=mergeable,
        outside_commits=outside,
    )


def run(prs, closed=(), cap=3, now=NOW):
    return plan(list(prs), list(closed), now, cap, AUTHORS, IDLE_DAYS, BASE)


def status_of(p: Plan, n):
    found = [(s, d) for (num, _sha, s, d) in p.statuses if num == n]
    if not found:
        return None
    assert len(found) == 1, found
    return found[0]


def idle_queue(days=10):
    """A preview-queue status history whose earliest entry is `days` old."""
    return ((NOW - timedelta(days=days), "success", "Preview slot held"),)


def fresh_queue(hours=1):
    """A recent first sighting; its text matches none of the planner's outputs
    used with it, so the planner's status counts as a change."""
    return ((NOW - timedelta(hours=hours), "success", "Queued for a preview slot (position 9 of 9)"),)


class TagFor(unittest.TestCase):
    def test_tag_for(self):
        self.assertEqual(tag_for(42, "abcdef0123456789"), "pr-42-abcdef0")


class Capacity(unittest.TestCase):
    def test_cap_respected(self):
        p = run([mk(n) for n in range(1, 6)], cap=3)
        self.assertEqual(p.add, [1, 2, 3])
        self.assertEqual(p.remove, [])

    def test_cap_zero_removes_all_labels(self):
        prs = [mk(1, labelled=True), mk(2, labelled=True), mk(3)]
        p = run(prs, cap=0)
        self.assertEqual(sorted(p.remove), [1, 2])
        self.assertEqual(p.add, [])

    def test_fifo_by_created_at(self):
        prs = [
            mk(1, created=NOW - timedelta(days=1)),
            mk(2, created=NOW - timedelta(days=3)),
            mk(3, created=NOW - timedelta(days=2)),
        ]
        p = run(prs, cap=2)
        self.assertEqual(p.add, [2, 3])
        self.assertEqual(status_of(p, 1), queued(1, 1))


class Built(unittest.TestCase):
    def test_holder_with_unbuilt_new_head_keeps_slot(self):
        holder = mk(1, labelled=True, built=False, queue=fresh_queue())
        p = run([holder, mk(2), mk(3)], cap=1)
        self.assertEqual(p.remove, [])
        self.assertEqual(p.add, [])
        self.assertEqual(status_of(p, 1), HELD)

    def test_unbuilt_pr_never_promoted(self):
        p = run([mk(1, built=False)], cap=3)
        self.assertEqual(p.add, [])
        self.assertEqual(status_of(p, 1), WAITING_IMAGES)

    def test_success_status_for_other_pr_tag_not_built(self):
        other = mk(1, images=("success", tag_for(2, sha(1))), manifests=True)
        p = run([other], cap=3)
        self.assertEqual(p.add, [])
        self.assertEqual(status_of(p, 1), WAITING_IMAGES)

    def test_missing_manifest_not_built(self):
        p = run([mk(1, manifests=False)], cap=3)
        self.assertEqual(p.add, [])
        self.assertEqual(status_of(p, 1), WAITING_IMAGES)

    def test_head_moved_after_build_is_not_built(self):
        old_head = sha(1, rev=0)
        moved = mk(1, rev=1, images=("success", tag_for(1, old_head)), manifests=True)
        self.assertIn(old_head[:7], moved.images_status[1])
        self.assertNotEqual(moved.head_sha[:7], old_head[:7])
        p = run([moved], cap=3)
        self.assertEqual(p.add, [])
        self.assertEqual(status_of(p, 1), WAITING_IMAGES)


class Eligibility(unittest.TestCase):
    def test_fork_nonallowlisted_nopreview_never_labelled_and_lose_label(self):
        fork = dict(head_repo="someone/DraftForge")
        stranger = dict(author="someone")
        optout = dict(labels=("no-preview",))
        prs = [mk(1, **fork), mk(2, **stranger), mk(3, **optout),
               mk(4, labelled=True, **fork), mk(5, labelled=True, **stranger),
               mk(6, labelled=True, **optout)]
        p = run(prs, cap=10)
        self.assertEqual(p.add, [])
        self.assertEqual(sorted(p.remove), [4, 5, 6])

    def test_author_substring_not_allowed(self):
        p = run([mk(1, author="kettle")], cap=3)
        self.assertEqual(p.add, [])

    def test_author_case_mismatch_not_allowed(self):
        p = run([mk(1, author="KettleOfKetchup", labelled=True)], cap=3)
        self.assertEqual(p.add, [])
        self.assertEqual(p.remove, [1])

    def test_two_prs_on_one_head_plan_independently(self):
        # Statuses are per SHA repo-wide; each PR reads only its own queue context
        # and its own image tag, so both are planned as if alone.
        a = mk(1)
        b = replace(mk(2), head_sha=a.head_sha,
                    images_status=("success", tag_for(2, a.head_sha)))
        p = run([a, b], cap=1)
        self.assertEqual(p.add, [1])
        self.assertEqual(status_of(p, 1), HELD)
        self.assertEqual(status_of(p, 2), queued(1, 1))

    def test_ineligible_with_queue_status_gets_not_eligible(self):
        was_queued = mk(1, labels=("no-preview",), queue=fresh_queue())
        never_seen = mk(2, author="someone")
        p = run([was_queued, never_seen], cap=3)
        self.assertEqual(status_of(p, 1), NOT_ELIGIBLE)
        self.assertIsNone(status_of(p, 2))


class OutsideCommits(unittest.TestCase):
    def test_outside_commit_never_labelled_and_loses_label(self):
        p = run([mk(1, outside=True), mk(2, labelled=True, outside=True)])
        self.assertEqual(p.add, [])
        self.assertEqual(p.remove, [2])
        self.assertEqual(status_of(p, 1), OUTSIDE)
        self.assertEqual(status_of(p, 2), OUTSIDE)

    def test_unchecked_commits_count_as_outside(self):
        p = run([mk(1, outside=None)])
        self.assertEqual(p.add, [])
        self.assertEqual(status_of(p, 1), OUTSIDE)

    def test_commits_outside(self):
        ok = (OWNER, OWNER, False)
        cases = [
            ([ok], False, False),
            ([ok, (OWNER, "web-flow", True)], False, False),
            ([ok, ("someone", OWNER, True)], False, True),
            ([ok, (OWNER, "someone", True)], False, True),
            ([ok, ("", OWNER, False)], False, True),
            ([], False, True),
            ([ok] * preview_queue.MAX_PR_COMMITS, False, True),
            ([ok], True, True),
            ([(OWNER, OWNER, True)], True, False),
        ]
        for commits, verified, want in cases:
            with self.subTest(commits=commits[:2], verified=verified):
                self.assertEqual(
                    preview_queue.commits_outside(commits, AUTHORS, verified), want)

    def test_parse_require_verified(self):
        self.assertFalse(preview_queue.parse_require_verified(""))
        self.assertFalse(preview_queue.parse_require_verified("false"))
        self.assertTrue(preview_queue.parse_require_verified("true"))
        for bad in ("yes", "True", "1", "true\n"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                preview_queue.parse_require_verified(bad)


class Closed(unittest.TestCase):
    def test_closed_labelled_loses_label(self):
        p = run([mk(1)], closed=[7], cap=3)
        self.assertEqual(p.remove, [7])
        self.assertEqual(p.add, [1])

    def test_closed_and_still_listed_not_counted(self):
        prs = [mk(1, labelled=True), mk(2)]
        p = run(prs, closed=[1], cap=1)
        self.assertIn(1, p.remove)
        self.assertNotIn(1, p.add)
        self.assertEqual(p.add, [2])  # 1 did not hold the only slot
        self.assertIsNone(status_of(p, 1))

    def test_reopened_waits_behind_earlier_waiters(self):
        # 5 is the oldest PR but was reopened, so it has no label: it is just
        # a waiter, ordered by created_at with nothing extra.
        holders = [mk(n, labelled=True) for n in (1, 2)]
        waiter = mk(3, created=NOW - timedelta(days=40))
        reopened = mk(5, created=NOW - timedelta(days=20))
        p = run([*holders, waiter, reopened], cap=2)
        self.assertEqual(p.add, [])
        self.assertEqual(status_of(p, 3), queued(1, 2))
        self.assertEqual(status_of(p, 5), queued(2, 2))


class OverCap(unittest.TestCase):
    def test_over_cap_keeps_earliest_grant_trims_hand_labelled_older(self):
        live = mk(5, labelled=True, grant=NOW - timedelta(days=5),
                  created=NOW - timedelta(days=5))
        hand = mk(1, labelled=True, grant=NOW - timedelta(minutes=1),
                  created=NOW - timedelta(days=60))
        p = run([live, hand], cap=1)
        self.assertEqual(p.remove, [1])
        self.assertEqual(p.add, [])
        self.assertEqual(status_of(p, 5), HELD)

    def test_over_cap_unknown_grant_time_trimmed_first(self):
        known = mk(1, labelled=True, grant=NOW - timedelta(minutes=1))
        unknown = replace(mk(2, labelled=True), grant_time=None)
        p = run([known, unknown], cap=1)
        self.assertEqual(p.remove, [2])


class Eviction(unittest.TestCase):
    def test_no_waiters_idle_or_failed_holder_kept(self):
        idle = mk(1, labelled=True, queue=idle_queue())
        failed = mk(2, labelled=True, built=False,
                    images=("failure", tag_for(2, sha(2))), queue=fresh_queue())
        p = run([idle, failed], cap=2)
        self.assertEqual(p.remove, [])
        self.assertEqual(p.add, [])

    def test_waiter_evicts_idle_holder_and_is_promoted(self):
        idle = mk(1, labelled=True, queue=idle_queue())
        busy = mk(2, labelled=True, queue=fresh_queue())
        p = run([idle, busy, mk(3)], cap=2)
        self.assertEqual(p.remove, [1])
        self.assertEqual(p.add, [3])
        self.assertEqual(status_of(p, 1), RELEASED)
        self.assertEqual(status_of(p, 3), HELD)

    def test_waiter_evicts_failed_holder(self):
        failed = mk(1, labelled=True, built=False,
                    images=("failure", tag_for(1, sha(1))), queue=fresh_queue())
        p = run([failed, mk(2)], cap=1)
        self.assertEqual(p.remove, [1])
        self.assertEqual(p.add, [2])
        self.assertEqual(status_of(p, 1), RELEASED)

    def test_conflicted_holder_is_evictable_when_waiters(self):
        conflicted = mk(1, labelled=True, mergeable=False, queue=fresh_queue())
        alone = run([conflicted], cap=1)
        self.assertEqual(alone.remove, [])
        self.assertEqual(status_of(alone, 1), CONFLICT)
        crowded = run([conflicted, mk(2)], cap=1)
        self.assertEqual(crowded.remove, [1])
        self.assertEqual(crowded.add, [2])
        self.assertEqual(status_of(crowded, 1), CONFLICT)

    def test_mergeable_none_is_not_failed(self):
        unknown = mk(1, labelled=True, mergeable=None, queue=fresh_queue())
        p = run([unknown, mk(2)], cap=1)
        self.assertEqual(p.remove, [])
        self.assertEqual(p.add, [])
        self.assertEqual(status_of(p, 1), HELD)

    def test_eviction_one_per_unserved_waiter(self):
        idle = [mk(n, labelled=True, queue=idle_queue(days=10 + n)) for n in (1, 2, 3)]
        p = run([*idle, mk(4)], cap=3)
        self.assertEqual(p.remove, [3])  # oldest idle head first, only one
        self.assertEqual(p.add, [4])

    def test_idle_waiters_sort_last(self):
        idle_waiter = mk(1, queue=idle_queue(), created=NOW - timedelta(days=50))
        fresh_waiter = mk(2, created=NOW - timedelta(days=2))
        p = run([idle_waiter, fresh_waiter], cap=1)
        self.assertEqual(p.add, [2])
        self.assertEqual(status_of(p, 1), queued(1, 1))


    def test_idle_waiter_does_not_displace_idle_holder(self):
        holder = mk(1, labelled=True, queue=idle_queue(days=12))
        waiter = mk(2, queue=idle_queue(days=10))
        p = run([holder, waiter], cap=1)
        self.assertEqual(p.remove, [])
        self.assertEqual(p.add, [])
        self.assertEqual(status_of(p, 1), None)  # already "held"
        self.assertEqual(status_of(p, 2), queued(1, 1))

    def test_idle_waiter_takes_failed_holders_slot(self):
        failed = mk(1, labelled=True, built=False,
                    images=("failure", tag_for(1, sha(1))), queue=fresh_queue())
        waiter = mk(2, queue=idle_queue())
        p = run([failed, waiter], cap=1)
        self.assertEqual(p.remove, [1])
        self.assertEqual(p.add, [2])

    def test_idle_holder_evicted_only_for_non_idle_waiters(self):
        # cap 2: an idle holder (oldest head) and a failed holder; one fresh
        # and two idle waiters. The failed holder goes first and its slot
        # serves the fresh waiter, so the idle holder stays: evicting it would
        # only hand its slot to an idle waiter.
        prs = [
            mk(1, labelled=True, queue=idle_queue(days=20)),
            mk(2, labelled=True, built=False,
               images=("failure", tag_for(2, sha(2))), queue=idle_queue(days=8)),
            mk(3, queue=fresh_queue()),
            mk(4, queue=idle_queue(days=9)),
            mk(5, queue=idle_queue(days=9)),
        ]
        p = run(prs, cap=2)
        self.assertEqual(p.remove, [2])
        self.assertEqual(p.add, [3])
        # Two fresh waiters: the idle holder is evicted for the second one.
        two_fresh = run([*prs[:3], mk(6, queue=fresh_queue()), *prs[3:]], cap=2)
        self.assertEqual(two_fresh.remove, [1, 2])
        self.assertEqual(two_fresh.add, [3, 6])
        # Only idle waiters: they may take only the failed holder's slot.
        only_idle = run([prs[0], prs[1], prs[3], prs[4]], cap=2)
        self.assertEqual(only_idle.remove, [2])
        self.assertEqual(only_idle.add, [4])

    def test_failed_holder_evicted_before_older_idle_holder(self):
        idle = mk(1, labelled=True, queue=idle_queue(days=20))
        conflicted = mk(2, labelled=True, mergeable=False, queue=idle_queue(days=8))
        p = run([idle, conflicted, mk(3, queue=fresh_queue())], cap=2)
        self.assertEqual(p.remove, [2])
        self.assertEqual(p.add, [3])

def simulate(prs, runs, cap=3, step=timedelta(minutes=10)):
    """Run the queue `runs` times, feeding each plan's label changes and
    statuses back into the PR records as GitHub would. Returns the plans."""
    state = {p.number: p for p in prs}
    plans = []
    for i in range(runs):
        now = NOW + step * i
        p = plan(list(state.values()), [], now, cap, AUTHORS, IDLE_DAYS, BASE)
        plans.append(p)
        for n in p.remove:
            state[n] = replace(state[n], labels=state[n].labels - {"preview-env"})
        for n in p.add:
            state[n] = replace(state[n], labels=state[n].labels | {"preview-env"},
                               grant_time=now)
        for n, _head, s, d in p.statuses:
            state[n] = replace(state[n],
                               queue_statuses=state[n].queue_statuses + ((now, s, d),))
    return plans


class Stability(unittest.TestCase):
    """The queue is level-triggered and runs every 10 minutes: once applied,
    a plan must not be undone by the next run on the same PR state."""

    def assert_fixed_point(self, plans):
        for i, p in enumerate(plans[1:], start=1):
            self.assertEqual((p.remove, p.add), ([], []), f"labels changed on run {i}")
        for i, p in enumerate(plans[2:], start=2):
            self.assertEqual(p.statuses, [], f"statuses changed on run {i}")

    def test_more_idle_prs_than_cap_do_not_swap(self):
        prs = [mk(1, labelled=True, queue=idle_queue(days=10), grant=NOW - timedelta(days=10)),
               mk(2, queue=idle_queue(days=10))]
        plans = simulate(prs, runs=6, cap=1)
        self.assertEqual((plans[0].remove, plans[0].add), ([], []))
        self.assert_fixed_point(plans)

    def test_fresh_waiter_evicts_once_then_stable(self):
        prs = [mk(1, labelled=True, queue=idle_queue()), mk(2, labelled=True, queue=idle_queue()),
               mk(3, queue=fresh_queue()), mk(4, queue=idle_queue()), mk(5, queue=idle_queue())]
        plans = simulate(prs, runs=6, cap=2)
        self.assertEqual(plans[0].add, [3])
        self.assertEqual(len(plans[0].remove), 1)
        self.assert_fixed_point(plans)

    def test_random_states_reach_fixed_point(self):
        import random
        rng = random.Random(20261107)
        for case in range(400):
            prs = []
            for n in range(1, rng.randint(1, 7) + 1):
                kind = rng.choice(["fresh", "idle", "failed", "conflict", "unbuilt", "none"])
                kw = {"labelled": rng.random() < 0.5}
                if kw["labelled"]:
                    kw["grant"] = NOW - timedelta(hours=rng.randint(1, 500))
                if kind == "fresh":
                    kw["queue"] = fresh_queue(hours=rng.randint(1, 100))
                elif kind == "idle":
                    kw["queue"] = idle_queue(days=rng.randint(8, 30))
                elif kind == "failed":
                    kw.update(built=False, images=("failure", tag_for(n, sha(n))),
                              queue=idle_queue(days=rng.randint(1, 30)))
                elif kind == "conflict":
                    kw.update(mergeable=False, queue=idle_queue(days=rng.randint(1, 30)))
                elif kind == "unbuilt":
                    kw.update(built=False, queue=fresh_queue(hours=rng.randint(1, 5)))
                prs.append(mk(n, **kw))
            cap = rng.randint(0, 4)
            with self.subTest(case=case, cap=cap, prs=[(p.number, sorted(p.labels)) for p in prs]):
                self.assert_fixed_point(simulate(prs, runs=5, cap=cap))


class Writes(unittest.TestCase):
    def test_removals_before_additions(self):
        prs = [mk(1, labelled=True, queue=idle_queue()), mk(2)]
        p = run(prs, closed=[9], cap=1)
        self.assertEqual(p.remove, [9, 1])  # closed first, then the rest
        self.assertEqual(p.add, [2])
        self.assertEqual(set(p.remove) & set(p.add), set())

    def test_human_removed_label_readded_when_winning(self):
        unlabelled = mk(1, queue=((NOW - timedelta(hours=1), *HELD),))
        p = run([unlabelled], cap=1)
        self.assertEqual(p.add, [1])
        self.assertIsNone(status_of(p, 1))  # its latest status is already "held"

    def test_statuses_only_written_on_change(self):
        older = NOW - timedelta(days=1)
        newer = NOW - timedelta(hours=1)
        same = mk(1, labelled=True,
                  queue=((older, *WAITING_IMAGES), (newer, *HELD)))
        # The latest status, not the earliest, is what "changed" compares to.
        changed = mk(2, labelled=True,
                     queue=((older, *HELD), (newer, *WAITING_IMAGES)))
        p = run([same, changed], cap=2)
        self.assertIsNone(status_of(p, 1))
        self.assertEqual(status_of(p, 2), HELD)
        self.assertEqual([s[1] for s in p.statuses if s[0] == 2], [sha(2)])

    def test_status_strings_exact(self):
        prs = [
            mk(1, labelled=True, queue=idle_queue()),                  # evicted
            mk(2, labelled=True, queue=fresh_queue()),                 # held
            mk(3),                                                     # promoted
            mk(4), mk(5),                                              # queued 1/2, 2/2
            mk(6, built=False, queue=fresh_queue()),                   # waiting images
            mk(7, built=False, images=("failure", tag_for(7, sha(7)))),  # failed
            mk(8, built=False, queue=fresh_queue(hours=3)),            # no build
            mk(9, author="someone", queue=fresh_queue()),              # not eligible
            mk(10, mergeable=False),                                   # conflict
        ]
        p = run(prs, cap=2)
        got = {n: status_of(p, n) for n in range(1, 11)}
        self.assertEqual(got, {
            1: ("success", "Preview slot released (idle or failed build); queued again"),
            2: ("success", "Preview slot held"),
            3: ("success", "Preview slot held"),
            4: ("success", "Queued for a preview slot (position 1 of 2)"),
            5: ("success", "Queued for a preview slot (position 2 of 2)"),
            6: ("pending", "Waiting for preview images"),
            7: ("failure", "Preview images failed for this commit"),
            8: ("success", "No preview build for this commit; push a commit "
                           "(or close and reopen) to build"),
            9: ("success", "Not eligible for a preview"),
            10: ("failure", "PR has merge conflicts; resolve them to build preview images"),
        })
        self.assertEqual(p.remove, [1])
        self.assertEqual(p.add, [3])
        for num, head, _s, _d in p.statuses:
            self.assertEqual(head, sha(num))

    def test_no_build_after_grace_resolves_status(self):
        late = run([mk(1, built=False, queue=fresh_queue(hours=3))], cap=3)
        self.assertEqual(late.add, [])
        self.assertEqual(status_of(late, 1), NO_BUILD)
        early = run([mk(1, built=False, queue=fresh_queue(hours=1))], cap=3)
        self.assertEqual(early.add, [])
        self.assertEqual(status_of(early, 1), WAITING_IMAGES)


class Config(unittest.TestCase):
    def test_parse_config_rejects(self):
        bad = [
            ("-1", OWNER, "7"), ("4", OWNER, "7"), ("11", OWNER, "7"), ("x", OWNER, "7"), ("", OWNER, "7"),
            ("3", "a, b", "7"), ("3", "a,,b", "7"), ("3", "", "7"), ("3", "bad_login", "7"),
            ("3", OWNER, "0"), ("3", OWNER, "x"), ("3", OWNER, ""), ("3", OWNER, "366"),
            ("3", "a,b\n", "7"), ("3", "kettleofketchup\n", "7"),
            ("3\n", OWNER, "7"), ("3", OWNER, "7\n"),
        ]
        for args in bad:
            with self.subTest(args=args), self.assertRaises(ValueError):
                parse_config(*args)

    def test_parse_config_accepts_zero(self):
        self.assertEqual(parse_config("0", OWNER, "7"), (0, frozenset({OWNER}), 7))
        self.assertEqual(
            parse_config("3", "kettleofketchup,other-user", "365"),
            (3, frozenset({"kettleofketchup", "other-user"}), 365),
        )


# --- I/O: the real GitHub client and GHCR check over a canned transport ---

API = "https://api.github.com"
TOKEN_JSON = json.dumps({"token": "anon-token"}).encode()


class Canned:
    """An Opener that replays (status, headers, body) responses in order and
    records every request it was given."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, req):
        self.requests.append(req)
        if not self.responses:
            raise AssertionError(f"unexpected request {req.get_method()} {req.full_url}")
        return self.responses.pop(0)

    def urls(self):
        return [r.full_url for r in self.requests]

    def writes(self):
        return [r for r in self.requests if r.get_method() not in ("GET", "HEAD")]


def page(items, next_url=None, status=200):
    headers = {"Link": f'<{next_url}>; rel="next", <{API}/x?page=9>; rel="last"'} if next_url else {}
    return (status, headers, json.dumps(items).encode())


def error(status=500):
    return (status, {}, b'{"message": "boom"}')


def pr_json(n, head, *, labels=(), login=OWNER, head_repo=BASE, draft=False,
            created="2026-10-01T00:00:00Z"):
    return {"number": n, "user": {"login": login}, "draft": draft, "created_at": created,
            "head": {"sha": head, "repo": {"full_name": head_repo}},
            "labels": [{"name": name} for name in labels]}


def status_json(context, state, description, created):
    return {"context": context, "state": state, "description": description,
            "created_at": created}


def label_event(name, created, event="labeled"):
    return {"event": event, "label": {"name": name}, "created_at": created}


def per_pr(n, *, events=None, statuses=([],), mergeable=True):
    """Responses one PR consumes after the PR list: issue events (only for a
    PR carrying preview-env), commit statuses, then GET /pulls/{n}."""
    out = []
    if events is not None:
        out += [page(items, next_url=nxt) for items, nxt in events]
    if statuses and isinstance(statuses[0], list):
        statuses = [(items, None) for items in statuses]
    out += [page(items, next_url=nxt) for items, nxt in statuses]
    out.append((200, {}, json.dumps({"number": n, "mergeable": mergeable}).encode()))
    return out


def dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def client(responses):
    opener = Canned(responses)
    return GitHub("secret-token", BASE, opener=opener), opener


class RealClient(unittest.TestCase):
    def test_real_client_paginates_link_next(self):
        nxt = f"{API}/repos/{BASE}/pulls?state=open&per_page=100&page=2"
        gh, opener = client(
            [page([pr_json(1, sha(1))], next_url=nxt), page([pr_json(2, sha(2))])]
            + per_pr(1) + per_pr(2))
        prs = gh.open_prs()
        self.assertEqual([p.number for p in prs], [1, 2])
        self.assertEqual(opener.urls()[1], nxt)
        self.assertEqual(opener.responses, [])
        self.assertEqual(opener.requests[0].get_header("Authorization"), "Bearer secret-token")

    def test_real_client_page2_500_raises(self):
        nxt = f"{API}/repos/{BASE}/pulls?state=open&per_page=100&page=2"
        gh, _ = client([page([pr_json(1, sha(1))], next_url=nxt), error(500)])
        with self.assertRaises(GitHubError):
            gh.open_prs()

    def test_real_client_reads_mergeable(self):
        for value in (True, False, None):
            with self.subTest(mergeable=value):
                gh, opener = client([page([pr_json(3, sha(3))])] + per_pr(3, mergeable=value))
                (pr,) = gh.open_prs()
                self.assertIs(pr.mergeable, value)
                self.assertEqual(opener.urls()[-1], f"{API}/repos/{BASE}/pulls/3")

    def test_real_client_builds_pr_fields(self):
        gh, _ = client([page([pr_json(4, sha(4), labels=("no-preview",), login="someone",
                                      head_repo="fork/DraftForge", draft=True,
                                      created="2026-10-02T03:04:05Z")])] + per_pr(4))
        (pr,) = gh.open_prs()
        self.assertEqual((pr.number, pr.author, pr.head_repo, pr.head_sha),
                         (4, "someone", "fork/DraftForge", sha(4)))
        self.assertEqual(pr.labels, frozenset({"no-preview"}))
        self.assertEqual(pr.created_at, dt("2026-10-02T03:04:05Z"))
        self.assertIsNone(pr.images_status)
        self.assertEqual(pr.queue_statuses, ())
        self.assertIsNone(pr.grant_time)
        self.assertIs(pr.manifests_exist, False)

    def test_grant_time_from_last_events_page(self):
        nxt = f"{API}/repos/{BASE}/issues/5/events?per_page=100&page=2"
        events = [
            ([label_event("preview-env", "2026-10-01T00:00:00Z")], nxt),
            ([label_event("preview-env", "2026-10-05T00:00:00Z"),
              label_event("other", "2026-10-06T00:00:00Z"),
              label_event("preview-env", "2026-10-07T00:00:00Z", event="unlabeled")], None),
        ]
        gh, opener = client([page([pr_json(5, sha(5), labels=("preview-env",))])]
                            + per_pr(5, events=events))
        (pr,) = gh.open_prs()
        self.assertEqual(pr.grant_time, dt("2026-10-05T00:00:00Z"))
        self.assertIn(nxt, opener.urls())

    def test_earliest_queue_status_from_last_statuses_page(self):
        nxt = f"{API}/repos/{BASE}/commits/{sha(6)}/statuses?per_page=100&page=2"
        statuses = [
            ([status_json("preview-queue/pr-6", "success", "Preview slot held",
                          "2026-10-05T00:00:00Z"),
              status_json("preview-queue/pr-6", "pending", "Waiting for preview images",
                          "2026-10-04T00:00:00Z")], nxt),
            ([status_json("preview-queue/pr-6", "pending", "Waiting for preview images",
                          "2026-10-01T00:00:00Z")], None),
        ]
        gh, _ = client([page([pr_json(6, sha(6))])] + per_pr(6, statuses=statuses))
        (pr,) = gh.open_prs()
        self.assertEqual(len(pr.queue_statuses), 3)
        self.assertEqual(min(t for t, _s, _d in pr.queue_statuses), dt("2026-10-01T00:00:00Z"))
        self.assertIn((dt("2026-10-05T00:00:00Z"), "success", "Preview slot held"),
                      pr.queue_statuses)

    def test_images_status_uses_latest_for_context(self):
        tag = tag_for(7, sha(7))
        statuses = [[
            status_json("preview-images", "success", tag, "2026-10-03T00:00:00Z"),
            status_json("preview-queue/pr-7", "pending", "Waiting for preview images",
                        "2026-10-02T12:00:00Z"),
            status_json("preview-images", "failure", tag, "2026-10-02T00:00:00Z"),
            status_json("preview-queue/pr-7", "pending", "Waiting for preview images",
                        "2026-10-01T00:00:00Z"),
        ]]
        gh, _ = client([page([pr_json(7, sha(7))])] + per_pr(7, statuses=statuses))
        (pr,) = gh.open_prs()
        self.assertEqual(pr.images_status, ("success", tag))

    def test_images_status_ignores_another_prs_tag(self):
        # PR 9 shares the head with another PR whose build posted last.
        tag = tag_for(9, sha(9))
        statuses = [[
            status_json("preview-images", "success", tag_for(10, sha(9)), "2026-10-03T00:00:00Z"),
            status_json("preview-images", "failure", tag, "2026-10-02T00:00:00Z"),
        ]]
        gh, _ = client([page([pr_json(9, sha(9))])] + per_pr(9, statuses=statuses))
        (pr,) = gh.open_prs()
        self.assertEqual(pr.images_status, ("failure", tag))

    def test_queue_statuses_ignore_another_prs_context(self):
        statuses = [[
            status_json("preview-queue/pr-10", "success", "Preview slot held",
                        "2026-10-01T00:00:00Z"),
            status_json("preview-queue", "success", "Preview slot held", "2026-09-01T00:00:00Z"),
        ]]
        gh, _ = client([page([pr_json(9, sha(9))])] + per_pr(9, statuses=statuses))
        (pr,) = gh.open_prs()
        self.assertEqual(pr.queue_statuses, ())

    def test_queue_statuses_filtered_to_own_context(self):
        statuses = [[
            status_json("preview-images", "success", "pr-8-x", "2026-10-03T00:00:00Z"),
            status_json("ci/test", "success", "ok", "2026-10-02T00:00:00Z"),
            status_json("preview-queue/pr-8", "success", "Preview slot held",
                        "2026-10-01T00:00:00Z"),
        ]]
        gh, _ = client([page([pr_json(8, sha(8))])] + per_pr(8, statuses=statuses))
        (pr,) = gh.open_prs()
        self.assertEqual(pr.queue_statuses,
                         ((dt("2026-10-01T00:00:00Z"), "success", "Preview slot held"),))

    def test_closed_search_paginates(self):
        nxt = f"{API}/search/issues?q=x&per_page=100&page=2"
        gh, opener = client([page({"total_count": 2, "items": [{"number": 4}]}, next_url=nxt),
                             page({"total_count": 2, "items": [{"number": 9}]})])
        self.assertEqual(gh.closed_labelled(), [4, 9])
        first = urllib.parse.urlsplit(opener.urls()[0])
        self.assertEqual(first.path, "/search/issues")
        self.assertEqual(urllib.parse.parse_qs(first.query)["q"],
                         [f"repo:{BASE} is:pr is:closed label:preview-env"])
        self.assertEqual(opener.urls()[1], nxt)

    def test_every_list_request_has_per_page_100(self):
        # The second PR's events `next` link lacks per_page; the client adds it.
        events = [([label_event("preview-env", "2026-10-01T00:00:00Z")],
                   f"{API}/repos/{BASE}/issues/2/events?page=2"),
                  ([], None)]
        gh, opener = client(
            [page([pr_json(1, sha(1)), pr_json(2, sha(2), labels=("preview-env",))])]
            + per_pr(1) + per_pr(2, events=events)
            + [page({"items": []})])
        gh.open_prs()
        gh.closed_labelled()
        self.assertEqual(opener.responses, [])
        details = {f"{API}/repos/{BASE}/pulls/1", f"{API}/repos/{BASE}/pulls/2"}
        lists = [u for u in opener.urls() if u not in details]
        self.assertEqual(len(lists), 6)
        for url in lists:
            with self.subTest(url=url):
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
                self.assertEqual(query["per_page"], ["100"])

    def test_next_link_to_other_host_rejected(self):
        gh, _ = client([page([pr_json(1, sha(1))], next_url="https://evil.example/steal")])
        with self.assertRaises(GitHubError):
            gh.open_prs()

    def test_set_status_and_label_request_shapes(self):
        gh, opener = client([(201, {}, b"{}"), (200, {}, b"[]"), (200, {}, b"[]"),
                             (404, {}, b"{}"), error(500)])
        gh.set_status(1, sha(1), "success", "Preview slot held")
        gh.add_label(5)
        gh.remove_label(5)
        gh.remove_label(6)  # 404: already gone, success
        with self.assertRaises(GitHubError):
            gh.remove_label(7)
        shapes = [(r.get_method(), r.full_url, json.loads(r.data) if r.data else None)
                  for r in opener.requests]
        self.assertEqual(shapes, [
            ("POST", f"{API}/repos/{BASE}/statuses/{sha(1)}",
             {"state": "success", "description": "Preview slot held",
              "context": "preview-queue/pr-1"}),
            ("POST", f"{API}/repos/{BASE}/issues/5/labels", {"labels": ["preview-env"]}),
            ("DELETE", f"{API}/repos/{BASE}/issues/5/labels/preview-env", None),
            ("DELETE", f"{API}/repos/{BASE}/issues/6/labels/preview-env", None),
            ("DELETE", f"{API}/repos/{BASE}/issues/7/labels/preview-env", None),
        ])
        for req in opener.requests[:2]:
            self.assertEqual(req.get_header("Content-type"), "application/json")

    def test_write_error_raises(self):
        for call in (lambda gh: gh.set_status(1, sha(1), "success", "x"),
                     lambda gh: gh.add_label(1)):
            gh, _ = client([error(422)])
            with self.assertRaises(GitHubError):
                call(gh)

    def test_from_env(self):
        gh = GitHub.from_env({"GH_TOKEN": "t", "GH_REPO": BASE})
        self.assertEqual((gh.token, gh.repo), ("t", BASE))
        for env in ({"GH_REPO": BASE}, {"GH_TOKEN": "t"}, {"GH_TOKEN": "", "GH_REPO": BASE}):
            with self.subTest(env=env), self.assertRaises(GitHubError):
                GitHub.from_env(env)


IMAGE = "kettleofketchup/draftforge-preview/backend"
TAG = "pr-12-0123456"


class ManifestExists(unittest.TestCase):
    def test_manifest_200_404_500(self):
        for status, expected in ((200, True), (404, False), (500, RegistryError)):
            with self.subTest(status=status):
                opener = Canned([(200, {}, TOKEN_JSON), (status, {}, b"")])
                if expected is RegistryError:
                    with self.assertRaises(RegistryError):
                        manifest_exists(IMAGE, TAG, opener=opener)
                else:
                    self.assertIs(manifest_exists(IMAGE, TAG, opener=opener), expected)
                token_req, head_req = opener.requests
                self.assertEqual(token_req.get_method(), "GET")
                self.assertEqual(token_req.full_url,
                                 f"https://ghcr.io/token?scope=repository:{IMAGE}:pull")
                self.assertEqual(head_req.get_method(), "HEAD")
                self.assertEqual(head_req.full_url,
                                 f"https://ghcr.io/v2/{IMAGE}/manifests/{TAG}")
                self.assertEqual(head_req.get_header("Authorization"), "Bearer anon-token")

    def test_manifest_token_error_raises(self):
        for resp in (error(500), (200, {}, b"not json"), (200, {}, b"{}")):
            with self.subTest(resp=resp):
                opener = Canned([resp])
                with self.assertRaises(RegistryError):
                    manifest_exists(IMAGE, TAG, opener=opener)
                self.assertEqual(len(opener.requests), 1)

    def test_manifest_accept_header_lists_four_types(self):
        opener = Canned([(200, {}, TOKEN_JSON), (200, {}, b"")])
        manifest_exists(IMAGE, TAG, opener=opener)
        accept = opener.requests[1].get_header("Accept")
        self.assertEqual(sorted(t.strip() for t in accept.split(",")), sorted([
            "application/vnd.oci.image.index.v1+json",
            "application/vnd.docker.distribution.manifest.list.v2+json",
            "application/vnd.oci.image.manifest.v1+json",
            "application/vnd.docker.distribution.manifest.v2+json",
        ]))


# --- main: fetch everything, then plan, then write ---

ENV = {"CAP": "3", "PREVIEW_AUTHORS": OWNER, "PREVIEW_IDLE_DAYS": "7", "CLOSED_PR": ""}


class FakeGitHub:
    repo = BASE

    def __init__(self, prs=(), closed=(), commits=None):
        self.prs = list(prs)
        self.closed = list(closed)
        self.commits = commits or {}
        self.commit_fetches = []
        self.fetched = False
        self.writes = []

    def pr_commits(self, n):
        self.commit_fetches.append(n)
        return self.commits.get(n, [(OWNER, OWNER, False)])

    def open_prs(self):
        self.fetched = True
        return list(self.prs)

    def closed_labelled(self):
        return list(self.closed)

    def remove_label(self, n):
        self.writes.append(("remove", n))

    def add_label(self, n):
        self.writes.append(("add", n))

    def set_status(self, n, head, state, desc):
        self.writes.append(("status", head, state, desc))


def always(_image, _tag):
    return True


def run_main(env, gh, manifests=always):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(env, gh, manifest_exists=manifests)
    return rc, out.getvalue(), err.getvalue()


def as_listed(p: PR) -> PR:
    """What GitHub.open_prs returns: manifests and commits are checked later, by main."""
    return replace(p, manifests_exist=False, outside_commits=None)


class Main(unittest.TestCase):
    def test_main_bad_cap_no_writes(self):
        bad = [dict(ENV, CAP="x"), dict(ENV, CAP="4"), dict(ENV, CAP=""),
               dict(ENV, PREVIEW_AUTHORS="a, b"), dict(ENV, PREVIEW_IDLE_DAYS="0"),
               dict(ENV, CLOSED_PR="abc"), {k: v for k, v in ENV.items() if k != "CAP"}]
        for env in bad:
            with self.subTest(env=env):
                gh = FakeGitHub([as_listed(mk(1, labelled=True, head_repo="fork/x"))])
                rc, _, err = run_main(env, gh)
                self.assertNotEqual(rc, 0)
                self.assertEqual(gh.writes, [])
                self.assertFalse(gh.fetched)
                self.assertIn("preview-queue:", err)

    def test_fetch_error_on_second_page_writes_nothing(self):
        stale = pr_json(1, sha(1), labels=("preview-env",), head_repo="fork/x")
        pulls_next = f"{API}/repos/{BASE}/pulls?state=open&per_page=100&page=2"
        search_next = f"{API}/search/issues?q=x&per_page=100&page=2"
        events = [([label_event("preview-env", "2026-10-01T00:00:00Z")], None)]
        cases = {
            "pulls": [page([stale], next_url=pulls_next), error(500)],
            "search": [page([stale])] + per_pr(1, events=events)
                      + [page({"items": [{"number": 9}]}, next_url=search_next), error(500)],
        }
        for name, responses in cases.items():
            with self.subTest(list=name):
                gh, opener = client(responses)
                rc, _, err = run_main(ENV, gh)
                self.assertNotEqual(rc, 0)
                self.assertEqual(opener.writes(), [])
                self.assertEqual(opener.responses, [])
                self.assertIn("500", err)

    def test_events_page2_500_writes_nothing(self):
        stale = pr_json(1, sha(1), labels=("preview-env",), head_repo="fork/x")
        nxt = f"{API}/repos/{BASE}/issues/1/events?per_page=100&page=2"
        gh, opener = client([page([stale]),
                             page([label_event("preview-env", "2026-10-01T00:00:00Z")],
                                  next_url=nxt),
                             error(500)])
        rc, _, _ = run_main(ENV, gh)
        self.assertNotEqual(rc, 0)
        self.assertEqual(opener.writes(), [])
        self.assertEqual(opener.urls()[-1], nxt)

    def test_closed_pr_dropped_from_open_list(self):
        holder = as_listed(mk(4, labelled=True))
        waiter = as_listed(mk(5))
        gh = FakeGitHub([holder, waiter])
        rc, _, _ = run_main(dict(ENV, CAP="1", CLOSED_PR="4"), gh)
        self.assertEqual(rc, 0)
        self.assertIn(("add", 5), gh.writes)
        # The closed PR loses its label in the same run, even before search sees it.
        self.assertEqual([w for w in gh.writes if 4 in w or holder.head_sha in w],
                         [("remove", 4)])
        self.assertLess(gh.writes.index(("remove", 4)), gh.writes.index(("add", 5)))
        # Without CLOSED_PR the holder keeps the only slot.
        gh = FakeGitHub([holder, waiter])
        run_main(dict(ENV, CAP="1"), gh)
        self.assertNotIn(("add", 5), gh.writes)

    def test_writes_in_plan_order(self):
        prs = [as_listed(mk(2)),
               as_listed(mk(3, labelled=True, labels=("no-preview",))),
               as_listed(mk(5, labelled=True, head_repo="fork/x"))]
        gh = FakeGitHub(prs, closed=[7])
        rc, _, _ = run_main(dict(ENV, CAP="1"), gh)
        self.assertEqual(rc, 0)
        labels = [w for w in gh.writes if w[0] in ("remove", "add")]
        self.assertEqual(labels, [("remove", 7), ("remove", 3), ("remove", 5), ("add", 2)])
        first_add = gh.writes.index(("add", 2))
        self.assertTrue(all(w[0] == "remove" for w in gh.writes[:first_add]))
        self.assertIn(("status", sha(2), "success", "Preview slot held"), gh.writes)

    def test_manifests_checked_for_both_images_of_built_heads_only(self):
        seen = []

        def record(image, tag):
            seen.append((image, tag))
            return image.endswith("/backend")  # frontend missing -> not built

        gh = FakeGitHub([as_listed(mk(2)), as_listed(mk(3, built=False))])
        rc, _, _ = run_main(ENV, gh, manifests=record)
        self.assertEqual(rc, 0)
        tag = tag_for(2, sha(2))
        self.assertEqual(sorted(seen), [
            ("kettleofketchup/draftforge-preview/backend", tag),
            ("kettleofketchup/draftforge-preview/frontend", tag),
        ])
        self.assertNotIn(("add", 2), gh.writes)

    def test_commits_checked_for_allowlisted_same_repo_prs_only(self):
        gh = FakeGitHub([as_listed(mk(2)), as_listed(mk(3)),
                         as_listed(mk(5, head_repo="fork/x")),
                         as_listed(mk(6, author="someone"))],
                        commits={3: [(OWNER, OWNER, False), ("someone", "someone", False)]})
        rc, _, _ = run_main(ENV, gh)
        self.assertEqual(rc, 0)
        self.assertEqual(sorted(gh.commit_fetches), [2, 3])
        self.assertIn(("add", 2), gh.writes)
        self.assertNotIn(("add", 3), gh.writes)
        self.assertIn(("status", sha(3), *OUTSIDE), gh.writes)

    def test_require_verified_refuses_unsigned_commits(self):
        gh = FakeGitHub([as_listed(mk(2))])
        rc, _, _ = run_main(dict(ENV, PREVIEW_REQUIRE_VERIFIED="true"), gh)
        self.assertEqual(rc, 0)
        self.assertNotIn(("add", 2), gh.writes)
        gh = FakeGitHub([as_listed(mk(2))], commits={2: [(OWNER, OWNER, True)]})
        run_main(dict(ENV, PREVIEW_REQUIRE_VERIFIED="true"), gh)
        self.assertIn(("add", 2), gh.writes)

    def test_bad_require_verified_no_writes(self):
        gh = FakeGitHub([as_listed(mk(2))])
        rc, _, err = run_main(dict(ENV, PREVIEW_REQUIRE_VERIFIED="yes"), gh)
        self.assertNotEqual(rc, 0)
        self.assertEqual(gh.writes, [])
        self.assertFalse(gh.fetched)

    def test_real_client_reads_commit_logins(self):
        commits = [
            {"author": {"login": OWNER}, "committer": {"login": "web-flow"},
             "commit": {"verification": {"verified": True}}},
            {"author": None, "committer": None, "commit": {}},
        ]
        gh, opener = client([page(commits)])
        self.assertEqual(gh.pr_commits(4), [(OWNER, "web-flow", True), ("", "", False)])
        self.assertIn(f"{API}/repos/{BASE}/pulls/4/commits", opener.urls()[0])

    def test_manifest_error_status_aborts(self):
        def failing(image, tag):
            opener = Canned([(200, {}, TOKEN_JSON), (500, {}, b"")])
            return preview_queue.manifest_exists(image, tag, opener=opener)

        gh = FakeGitHub([as_listed(mk(2)), as_listed(mk(5, labelled=True, head_repo="fork/x"))])
        rc, _, err = run_main(ENV, gh, manifests=failing)
        self.assertNotEqual(rc, 0)
        self.assertEqual(gh.writes, [])
        self.assertIn("500", err)


if __name__ == "__main__":
    unittest.main()
