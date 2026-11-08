import copy
import json
import subprocess
import sys
import unittest
from decimal import Decimal

from scripts import helm_budget_check as bc
from scripts.preview_tests import _util

SCRIPT = _util.REPO_ROOT / "scripts" / "helm_budget_check.py"
CHART = _util.REPO_ROOT / "helm"


def render(*helm_args):
    """helm template the chart and return the docs as a JSON list (via yq)."""
    helm = _util.helm()
    _util.require(_util.which("yq"), "yq")
    out = subprocess.run(
        [helm, "template", "draftforge-pr-1", str(CHART), *helm_args],
        check=True, capture_output=True, text=True,
    ).stdout
    docs = subprocess.run(
        ["yq", "-o=json", "ea", "[.]"],
        input=out, check=True, capture_output=True, text=True,
    ).stdout
    return json.loads(docs)


def render_preview():
    return render(
        "-f", str(CHART / "values-preview.yaml"),
        "-f", str(CHART / "tests" / "fixtures" / "preview-appset-values.yaml"),
        "--namespace", "draftforge-pr-1",
    )


def run_check(docs):
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT)],
        input=json.dumps(docs), capture_output=True, text=True,
    )


def quota(**hard):
    base = {"requests.cpu": "1", "requests.memory": "2Gi",
            "requests.ephemeral-storage": "1Gi", "limits.cpu": "4",
            "limits.memory": "4Gi", "limits.ephemeral-storage": "4Gi", "pods": "8"}
    base.update(hard)
    return {"apiVersion": "v1", "kind": "ResourceQuota",
            "metadata": {"name": "q"}, "spec": {"hard": base}}


def res(cpu, mem, lim, lim_cpu="500m", eph="64Mi", lim_eph="256Mi"):
    return {"requests": {"cpu": cpu, "memory": mem, "ephemeral-storage": eph},
            "limits": {"cpu": lim_cpu, "memory": lim, "ephemeral-storage": lim_eph}}


def limit_range(**maxes):
    return {"apiVersion": "v1", "kind": "LimitRange", "metadata": {"name": "lr"},
            "spec": {"limits": [{"type": "Container", "max": maxes}]}}


def deployment(containers, init=None, replicas=1, strategy=None):
    spec = {"containers": containers}
    if init is not None:
        spec["initContainers"] = init
    d = {"apiVersion": "apps/v1", "kind": "Deployment",
         "metadata": {"name": "d"},
         "spec": {"replicas": replicas, "template": {"spec": spec}}}
    if strategy is not None:
        d["spec"]["strategy"] = strategy
    return d


class PreviewRenderTest(unittest.TestCase):
    def test_preview_render_fits(self):
        r = run_check(render_preview())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.splitlines(), [
            "requests.cpu 750m/1000m",
            "requests.memory 1728Mi/2048Mi",
            "requests.ephemeral-storage 768Mi/1024Mi",
            "limits.cpu 3700m/4000m",
            "limits.memory 3712Mi/4096Mi",
            "limits.ephemeral-storage 6144Mi/7168Mi",
            "pods 6/8",
        ])

    def test_over_quota_fails(self):
        docs = render_preview()
        for d in docs:
            if d and d.get("kind") == "ResourceQuota":
                d["spec"]["hard"]["requests.cpu"] = "500m"
        r = run_check(docs)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("requests.cpu 750m/500m", r.stdout.splitlines())

    def test_no_quota_fails(self):
        r = run_check(render())
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("no ResourceQuota", r.stdout + r.stderr)


class SyntheticBudgetTest(unittest.TestCase):
    def test_init_container_max_rule(self):
        docs = [quota(), deployment(
            [dict(name="c", resources=res("100m", "128Mi", "256Mi"))],
            init=[dict(name="i", resources=res("400m", "512Mi", "1Gi"))],
            strategy={"type": "Recreate"},
        )]
        r = run_check(docs)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.splitlines(), [
            "requests.cpu 400m/1000m",
            "requests.memory 512Mi/2048Mi",
            "requests.ephemeral-storage 64Mi/1024Mi",
            "limits.cpu 500m/4000m",
            "limits.memory 1024Mi/4096Mi",
            "limits.ephemeral-storage 256Mi/4096Mi",
            "pods 1/8",
        ])

    def test_containers_sum_when_larger_than_init(self):
        docs = [quota(), deployment(
            [dict(name="a", resources=res("300m", "256Mi", "256Mi")),
             dict(name="b", resources=res("300m", "256Mi", "256Mi"))],
            init=[dict(name="i", resources=res("400m", "128Mi", "128Mi"))],
            strategy={"type": "Recreate"},
        )]
        totals = bc.budget(docs)
        self.assertEqual(totals["requests.cpu"][0], Decimal("0.6"))
        self.assertEqual(totals["requests.memory"][0], 512 * 2**20)

    def test_surge_pods_are_charged(self):
        dep = deployment([dict(name="c", resources=res("100m", "128Mi", "256Mi"))],
                         strategy={"type": "RollingUpdate",
                                   "rollingUpdate": {"maxSurge": 1}})
        totals = bc.budget([quota(), dep])
        self.assertEqual(totals["pods"], (Decimal(2), Decimal(8)))
        self.assertEqual(totals["requests.cpu"][0], Decimal("0.2"))

    def test_budget_returns_hard_from_quota(self):
        totals = bc.budget([quota(pods="5")])
        self.assertEqual(totals["pods"], (Decimal(0), Decimal(5)))
        self.assertEqual(totals["limits.memory"], (Decimal(0), Decimal(4 * 2**30)))

    def test_parse_quantity(self):
        self.assertEqual(bc.parse_quantity("1"), bc.parse_quantity("1000m"))
        self.assertEqual(bc.parse_quantity("2Gi"), bc.parse_quantity("2048Mi"))
        self.assertEqual(bc.parse_quantity("500m"), Decimal("0.5"))
        self.assertEqual(bc.parse_quantity("1k"), Decimal(1000))
        self.assertEqual(bc.parse_quantity("1M"), Decimal(10**6))
        self.assertEqual(bc.parse_quantity("1G"), Decimal(10**9))
        self.assertEqual(bc.parse_quantity("1Ki"), Decimal(1024))
        for bad in ("", "1x", "Mi", "1.2.3"):
            with self.assertRaises(ValueError, msg=bad):
                bc.parse_quantity(bad)

    def test_surge_rules(self):
        def d(replicas, strategy):
            return deployment([], replicas=replicas, strategy=strategy)

        ru = lambda s: {"type": "RollingUpdate", "rollingUpdate": {"maxSurge": s}}
        self.assertEqual(bc.surge_pods(d(1, None)), 1)
        self.assertEqual(bc.surge_pods(d(1, {"type": "RollingUpdate"})), 1)
        self.assertEqual(bc.surge_pods(d(4, ru("25%"))), 1)
        self.assertEqual(bc.surge_pods(d(3, ru("50%"))), 2)
        self.assertEqual(bc.surge_pods(d(1, ru(0))), 0)
        self.assertEqual(bc.surge_pods(d(1, ru(2))), 2)
        self.assertEqual(bc.surge_pods(d(1, {"type": "Recreate"})), 0)

    def test_container_missing_limit_fails(self):
        r = res("1m", "1Mi", "1Mi")
        del r["limits"]["memory"]
        docs = [quota(), deployment([dict(name="c", resources=r)],
                                    strategy={"type": "Recreate"})]
        r = run_check(docs)
        self.assertEqual(r.returncode, 1)
        self.assertIn("limits.memory", r.stderr)

    def test_container_missing_ephemeral_limit_fails(self):
        r = res("1m", "1Mi", "1Mi")
        del r["limits"]["ephemeral-storage"]
        docs = [quota(), deployment([dict(name="c", resources=r)],
                                    strategy={"type": "Recreate"})]
        out = run_check(docs)
        self.assertEqual(out.returncode, 1)
        self.assertIn("limits.ephemeral-storage", out.stderr)

    def test_quota_without_ephemeral_key_fails(self):
        q = quota()
        del q["spec"]["hard"]["limits.ephemeral-storage"]
        out = run_check([q])
        self.assertEqual(out.returncode, 1)
        self.assertIn("limits.ephemeral-storage", out.stderr)

    def test_ephemeral_over_quota_fails(self):
        docs = [quota(**{"limits.ephemeral-storage": "128Mi"}), deployment(
            [dict(name="c", resources=res("1m", "1Mi", "1Mi"))],
            strategy={"type": "Recreate"})]
        out = run_check(docs)
        self.assertEqual(out.returncode, 1)
        self.assertIn("limits.ephemeral-storage 256Mi/128Mi", out.stdout.splitlines())

    def test_container_above_limit_range_max_fails(self):
        docs = [quota(), limit_range(cpu="250m"), deployment(
            [dict(name="c", resources=res("100m", "1Mi", "1Mi", lim_cpu="500m"))],
            strategy={"type": "Recreate"})]
        out = run_check(docs)
        self.assertEqual(out.returncode, 1)
        self.assertIn("exceeds the LimitRange max", out.stderr)

    def test_init_container_above_limit_range_max_fails(self):
        docs = [quota(), limit_range(memory="64Mi"), deployment(
            [dict(name="c", resources=res("1m", "1Mi", "32Mi"))],
            init=[dict(name="i", resources=res("1m", "1Mi", "128Mi"))],
            strategy={"type": "Recreate"})]
        out = run_check(docs)
        self.assertEqual(out.returncode, 1)
        self.assertIn("'i'", out.stderr)

    def test_container_within_limit_range_max_passes(self):
        docs = [quota(), limit_range(cpu="500m", memory="1Gi", **{"ephemeral-storage": "256Mi"}),
                deployment([dict(name="c", resources=res("100m", "1Mi", "1Mi"))],
                           strategy={"type": "Recreate"})]
        out = run_check(docs)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_unbudgeted_workload_kind_fails(self):
        r = run_check([quota(), {"kind": "StatefulSet", "metadata": {"name": "s"}}])
        self.assertEqual(r.returncode, 1)
        self.assertIn("StatefulSet", r.stderr)


if __name__ == "__main__":
    unittest.main()
