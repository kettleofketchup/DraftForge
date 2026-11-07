#!/usr/bin/env python3
"""Check that a rendered preview fits its own ResourceQuota, rollout surge included.

Reads a JSON array of rendered documents on stdin:

    "$HELM" template ... | yq -o=json ea '[.]' | python3 -I scripts/helm_budget_check.py

Sums requests.cpu, requests.memory and limits.memory over every Deployment pod,
plus one Deployment pod per surge pod, and compares them with the `hard` of the
single rendered ResourceQuota. Exit 0 when every total fits, 1 otherwise or
when there is no ResourceQuota.
"""
import json
import math
import re
import sys
from decimal import Decimal

KEYS = ("requests.cpu", "requests.memory", "limits.memory", "pods")
# Kinds that create pods; this check only knows how to charge Deployments.
POD_KINDS = {"Pod", "ReplicaSet", "ReplicationController", "StatefulSet",
             "DaemonSet", "Job", "CronJob"}
SUFFIXES = {
    "m": Decimal("0.001"), "": Decimal(1),
    "k": Decimal(10) ** 3, "M": Decimal(10) ** 6, "G": Decimal(10) ** 9,
    "T": Decimal(10) ** 12, "P": Decimal(10) ** 15, "E": Decimal(10) ** 18,
    "Ki": Decimal(2) ** 10, "Mi": Decimal(2) ** 20, "Gi": Decimal(2) ** 30,
    "Ti": Decimal(2) ** 40, "Pi": Decimal(2) ** 50, "Ei": Decimal(2) ** 60,
}
QUANTITY = re.compile(r"^(\d+(?:\.\d+)?|\.\d+)(m|k|M|G|T|P|E|Ki|Mi|Gi|Ti|Pi|Ei)?$")
MI = Decimal(2) ** 20


class BudgetError(Exception):
    pass


def parse_quantity(s) -> Decimal:
    """Parse a Kubernetes quantity ("500m", "2Gi", "1") into base units."""
    m = QUANTITY.match(str(s).strip())
    if not m:
        raise ValueError(f"invalid quantity: {s!r}")
    return Decimal(m.group(1)) * SUFFIXES[m.group(2) or ""]


def container_charge(c: dict, where: str) -> dict:
    res = c.get("resources") or {}
    out = {}
    for key in KEYS[:3]:
        section, name = key.split(".")
        value = (res.get(section) or {}).get(name)
        if value is None:
            raise BudgetError(f"{where} container {c.get('name')!r} has no {key}")
        out[key] = parse_quantity(value)
    return out


def pod_charge(deploy: dict) -> dict:
    """Per-pod charge, quota rule: max(sum over containers, max over initContainers)."""
    name = deploy.get("metadata", {}).get("name")
    spec = deploy.get("spec", {}).get("template", {}).get("spec", {})
    main = [container_charge(c, f"Deployment {name}") for c in spec.get("containers") or []]
    init = [container_charge(c, f"Deployment {name}") for c in spec.get("initContainers") or []]
    return {
        k: max(sum((c[k] for c in main), Decimal(0)),
               max((c[k] for c in init), default=Decimal(0)))
        for k in KEYS[:3]
    }


def surge_pods(deploy: dict) -> int:
    """Extra pods a rollout may create, using the Kubernetes defaults."""
    spec = deploy.get("spec", {})
    replicas = int(spec.get("replicas", 1))
    strategy = spec.get("strategy") or {}
    stype = strategy.get("type", "RollingUpdate")
    if stype == "Recreate":
        return 0
    if stype != "RollingUpdate":
        raise BudgetError(f"unknown Deployment strategy {stype!r}")
    surge = (strategy.get("rollingUpdate") or {}).get("maxSurge", "25%")
    if isinstance(surge, bool):
        raise BudgetError(f"invalid maxSurge {surge!r}")
    if isinstance(surge, int):
        return surge
    m = re.fullmatch(r"(\d+)%", str(surge))
    if not m:
        raise BudgetError(f"invalid maxSurge {surge!r}")
    return math.ceil(replicas * int(m.group(1)) / 100)


def budget(docs: list) -> dict:
    """Return {key: (total, hard)} in base units (cores, bytes, pods)."""
    docs = [d for d in docs if isinstance(d, dict) and d]
    quotas = [d for d in docs if d.get("kind") == "ResourceQuota"]
    if not quotas:
        raise BudgetError("no ResourceQuota in the render")
    if len(quotas) > 1:
        raise BudgetError(f"expected one ResourceQuota, found {len(quotas)}")
    hard_spec = quotas[0].get("spec", {}).get("hard") or {}
    missing = [k for k in KEYS if k not in hard_spec]
    if missing:
        raise BudgetError(f"ResourceQuota hard lacks {', '.join(missing)}")
    hard = {k: parse_quantity(hard_spec[k]) for k in KEYS}

    totals = {k: Decimal(0) for k in KEYS}
    for d in docs:
        kind = d.get("kind")
        if kind in POD_KINDS:
            raise BudgetError(f"{kind} {d.get('metadata', {}).get('name')!r} "
                              "creates pods this check does not budget")
        if kind != "Deployment":
            continue
        pods = int(d.get("spec", {}).get("replicas", 1)) + surge_pods(d)
        charge = pod_charge(d)
        for k in KEYS[:3]:
            totals[k] += charge[k] * pods
        totals["pods"] += pods
    return {k: (totals[k], hard[k]) for k in KEYS}


def _num(d: Decimal) -> str:
    d = d.normalize()
    return f"{d:f}" if d != d.to_integral_value() else str(int(d))


def fmt(key: str, value: Decimal) -> str:
    if key == "requests.cpu":
        return _num(value * 1000) + "m"
    if key == "pods":
        return _num(value)
    return _num(value / MI) + "Mi"


def main() -> int:
    try:
        docs = json.load(sys.stdin)
        if not isinstance(docs, list):
            raise BudgetError("stdin must be a JSON array of rendered documents")
        result = budget(docs)
    except (BudgetError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    ok = True
    for key in KEYS:
        total, hard = result[key]
        print(f"{key} {fmt(key, total)}/{fmt(key, hard)}")
        ok = ok and total <= hard
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
