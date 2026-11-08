#!/usr/bin/env python3
"""Check that a rendered preview fits its own ResourceQuota, rollout surge included.

Reads a JSON array of rendered documents on stdin:

    "$HELM" template ... | yq -o=json ea '[.]' | python3 -I scripts/helm_budget_check.py

Sums cpu, memory and ephemeral-storage requests and limits over every
Deployment pod, plus one Deployment pod per surge pod, and compares them with
the `hard` of the single rendered ResourceQuota. When a LimitRange is rendered,
also checks every container's requests and limits against its Container `max`,
since admission rejects a pod above it. Also counts the rendered objects for
every object-count key in `hard` (services, secrets, configmaps,
services.loadbalancers, services.nodeports and count/<resource>[.<group>]),
plus the objects Kubernetes adds to every namespace (the kube-root-ca.crt
ConfigMap and the default ServiceAccount), since quota admission rejects an
object over its count at sync time. Exit 0 when everything fits, 1 otherwise
or when there is no ResourceQuota.
"""
import json
import math
import re
import sys
from decimal import Decimal

RESOURCE_KEYS = ("requests.cpu", "requests.memory", "requests.ephemeral-storage",
                 "limits.cpu", "limits.memory", "limits.ephemeral-storage")
KEYS = RESOURCE_KEYS + ("pods",)
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
# Short object-count quota names for core resources.
CORE_COUNT_KEYS = {"services", "secrets", "configmaps", "persistentvolumeclaims",
                   "replicationcontrollers", "resourcequotas"}
# Objects every namespace gets without the chart: (resource, group) -> count.
IMPLICIT_OBJECTS = {("configmaps", ""): 1, ("serviceaccounts", ""): 1}
# Kinds that are not namespaced, so no namespace quota counts them.
CLUSTER_KINDS = {"Namespace", "ClusterRole", "ClusterRoleBinding", "PriorityClass",
                 "CustomResourceDefinition", "StorageClass", "PersistentVolume"}


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
    for key in RESOURCE_KEYS:
        section, name = key.split(".")
        value = (res.get(section) or {}).get(name)
        if value is None:
            raise BudgetError(f"{where} container {c.get('name')!r} has no {key}")
        out[key] = parse_quantity(value)
    return out


def check_limit_range_max(docs: list) -> None:
    """Raise when a container's request or limit exceeds the LimitRange Container max."""
    maxes = {}
    for d in docs:
        if d.get("kind") != "LimitRange":
            continue
        for item in d.get("spec", {}).get("limits") or []:
            if item.get("type") == "Container":
                for name, value in (item.get("max") or {}).items():
                    q = parse_quantity(value)
                    maxes[name] = min(q, maxes.get(name, q))
    if not maxes:
        return
    for d in docs:
        if d.get("kind") != "Deployment":
            continue
        name = d.get("metadata", {}).get("name")
        spec = d.get("spec", {}).get("template", {}).get("spec", {})
        for c in (spec.get("initContainers") or []) + (spec.get("containers") or []):
            res = c.get("resources") or {}
            for section in ("requests", "limits"):
                for res_name, value in (res.get(section) or {}).items():
                    if res_name in maxes and parse_quantity(value) > maxes[res_name]:
                        raise BudgetError(
                            f"Deployment {name} container {c.get('name')!r} {section}.{res_name} "
                            f"{value} exceeds the LimitRange max")


def pod_charge(deploy: dict) -> dict:
    """Per-pod charge, quota rule: max(sum over containers, max over initContainers)."""
    name = deploy.get("metadata", {}).get("name")
    spec = deploy.get("spec", {}).get("template", {}).get("spec", {})
    main = [container_charge(c, f"Deployment {name}") for c in spec.get("containers") or []]
    init = [container_charge(c, f"Deployment {name}") for c in spec.get("initContainers") or []]
    return {
        k: max(sum((c[k] for c in main), Decimal(0)),
               max((c[k] for c in init), default=Decimal(0)))
        for k in RESOURCE_KEYS
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
        for k in RESOURCE_KEYS:
            totals[k] += charge[k] * pods
        totals["pods"] += pods
    check_limit_range_max(docs)
    return {k: (totals[k], hard[k]) for k in KEYS}


def resource_of(doc: dict) -> tuple[str, str]:
    """(plural resource, API group) of a rendered object, e.g. ("middlewares", "traefik.io")."""
    kind = doc.get("kind", "").lower()
    if kind.endswith("y"):
        plural = kind[:-1] + "ies"
    elif kind.endswith("s"):
        plural = kind + "es"
    else:
        plural = kind + "s"
    api = doc.get("apiVersion", "")
    group = api.rsplit("/", 1)[0] if "/" in api else ""
    return plural, group


def count_key(key: str) -> tuple[str, str] | None:
    """(resource, group) an object-count quota key limits, or None for a compute key."""
    if key in CORE_COUNT_KEYS:
        return key, ""
    if key.startswith("count/"):
        resource, _, group = key[len("count/"):].partition(".")
        return resource, group
    return None


def object_counts(docs: list) -> dict:
    """Return {key: (count, hard)} for every object-count key in the ResourceQuota."""
    docs = [d for d in docs if isinstance(d, dict) and d]
    quotas = [d for d in docs if d.get("kind") == "ResourceQuota"]
    if len(quotas) != 1:
        raise BudgetError(f"expected one ResourceQuota, found {len(quotas)}")
    hard_spec = quotas[0].get("spec", {}).get("hard") or {}
    rendered: dict[tuple[str, str], int] = dict(IMPLICIT_OBJECTS)
    service_types: dict[str, int] = {}
    for d in docs:
        if d.get("kind") in CLUSTER_KINDS:
            continue
        r = resource_of(d)
        rendered[r] = rendered.get(r, 0) + 1
        if d.get("kind") == "Service":
            stype = d.get("spec", {}).get("type", "ClusterIP")
            service_types[stype] = service_types.get(stype, 0) + 1
    out = {}
    for key, value in hard_spec.items():
        if key == "services.loadbalancers":
            n = service_types.get("LoadBalancer", 0)
        elif key == "services.nodeports":
            n = service_types.get("NodePort", 0) + service_types.get("LoadBalancer", 0)
        elif (target := count_key(key)) is not None:
            n = rendered.get(target, 0)
        else:
            continue
        out[key] = (n, int(parse_quantity(value)))
    return out


def _num(d: Decimal) -> str:
    d = d.normalize()
    return f"{d:f}" if d != d.to_integral_value() else str(int(d))


def fmt(key: str, value: Decimal) -> str:
    if key.endswith(".cpu"):
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
        counts = object_counts(docs)
    except (BudgetError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    ok = True
    for key in KEYS:
        total, hard = result[key]
        print(f"{key} {fmt(key, total)}/{fmt(key, hard)}")
        ok = ok and total <= hard
    for key in sorted(counts):
        n, hard = counts[key]
        print(f"{key} {n}/{hard}")
        ok = ok and n <= hard
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
