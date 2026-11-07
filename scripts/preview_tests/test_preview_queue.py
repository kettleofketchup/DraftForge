"""Pure-function tests for the preview queue planner (spec §5.6).

Every case builds `PR` records by hand and calls `plan()` directly; no I/O.
"""
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from scripts.preview_queue import PR, Plan, parse_config, plan, tag_for

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
CONFLICT = ("failure", "PR has merge conflicts; resolve them to build preview images")


def queued(k, m):
    return ("success", f"Queued for a preview slot (position {k} of {m})")


def sha(n, rev=0):
    """Head SHA of PR n; `rev` changes the first 7 chars (the tag part)."""
    return f"{n:04d}{rev:03d}" + "a" * 33


def mk(n, *, built=True, labelled=False, author=OWNER, head_repo=BASE, rev=0,
       labels=(), draft=False, created=None, images=None, manifests=None,
       queue=(), grant=None, mergeable=True):
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
        draft=draft,
        labels=frozenset(lbls),
        created_at=created or (NOW - timedelta(days=30) + timedelta(hours=n)),
        images_status=images,
        queue_statuses=tuple(queue),
        grant_time=grant,
        manifests_exist=manifests,
        mergeable=mergeable,
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

    def test_draft_pr_allowed(self):
        p = run([mk(1, draft=True)], cap=3)
        self.assertEqual(p.add, [1])

    def test_ineligible_with_queue_status_gets_not_eligible(self):
        was_queued = mk(1, labels=("no-preview",), queue=fresh_queue())
        never_seen = mk(2, author="someone")
        p = run([was_queued, never_seen], cap=3)
        self.assertEqual(status_of(p, 1), NOT_ELIGIBLE)
        self.assertIsNone(status_of(p, 2))


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
            ("-1", OWNER, "7"), ("11", OWNER, "7"), ("x", OWNER, "7"), ("", OWNER, "7"),
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
            parse_config("10", "kettleofketchup,other-user", "365"),
            (10, frozenset({"kettleofketchup", "other-user"}), 365),
        )


if __name__ == "__main__":
    unittest.main()
