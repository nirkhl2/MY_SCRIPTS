#!/usr/bin/env python3
"""
Pod debug report — shows status, restarts, actual CPU/MEM usage vs requests/limits, and recent errors.

Usage:
  python3 pod_report.py                          # all namespaces
  python3 pod_report.py -n my-namespace          # filter by namespace
  python3 pod_report.py -d my-deployment         # filter by deployment name
  python3 pod_report.py -n my-ns -d my-svc       # both
  python3 pod_report.py --errors-only            # only show pods with restarts/errors
"""

import subprocess, json, sys, argparse
from datetime import datetime, timezone

def run(cmd):
    return subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode()

parser = argparse.ArgumentParser()
parser.add_argument("-n", "--namespace", default=None)
parser.add_argument("-d", "--deployment", default=None)
parser.add_argument("--errors-only", action="store_true", help="Only show pods with restarts or non-Running status")
args = parser.parse_args()

ns_flag = f"-n {args.namespace}" if args.namespace else "-A"

print("Fetching pod data...")

pods_json  = json.loads(run(f"kubectl get pods {ns_flag} -o json"))
top_raw    = run(f"kubectl top pods {ns_flag} --no-headers 2>/dev/null || true")
events_raw = json.loads(run(f"kubectl get events {ns_flag} -o json"))

# --- parse kubectl top pods ---
# format: NAMESPACE  NAME  CPU  MEM  (when -A) or NAME  CPU  MEM (when -n)
top_map = {}
for line in top_raw.strip().splitlines():
    parts = line.split()
    if not parts:
        continue
    if args.namespace:
        # NAME CPU MEM
        if len(parts) >= 3:
            top_map[parts[0]] = {"cpu": parts[1], "mem": parts[2]}
    else:
        # NAMESPACE NAME CPU MEM
        if len(parts) >= 4:
            top_map[f"{parts[0]}/{parts[1]}"] = {"cpu": parts[2], "mem": parts[3]}

# --- parse events: group warnings by pod name ---
warn_map = {}
for ev in events_raw.get("items", []):
    if ev.get("type") != "Warning":
        continue
    ref  = ev.get("involvedObject", {})
    pkey = f"{ref.get('namespace','')}/{ref.get('name','')}"
    reason  = ev.get("reason", "")
    message = ev.get("message", "")[:80]
    warn_map.setdefault(pkey, []).append(f"{reason}: {message}")

# --- header ---
print("=" * 170)
print(f"{'NAMESPACE':<20} {'POD':<55} {'STATUS':<12} {'READY':<7} {'RESTARTS':>8}  "
      f"{'CPU_ACT':>8} {'CPU_REQ':>9} {'CPU_LIM':>9}   {'MEM_ACT':>9} {'MEM_REQ':>9} {'MEM_LIM':>9}  {'WARNINGS'}")
print("=" * 170)

# --- process pods ---
found = 0
for pod in pods_json["items"]:
    ns   = pod["metadata"]["namespace"]
    name = pod["metadata"]["name"]

    # filter by deployment/app name
    if args.deployment:
        owner = pod["metadata"].get("labels", {})
        app_label = owner.get("app", owner.get("app.kubernetes.io/name", ""))
        # also check ownerReferences name prefix
        owners = [o["name"] for o in pod["metadata"].get("ownerReferences", [])]
        match = (
            args.deployment.lower() in name.lower() or
            args.deployment.lower() in app_label.lower() or
            any(args.deployment.lower() in o.lower() for o in owners)
        )
        if not match:
            continue

    # status
    phase    = pod["status"].get("phase", "Unknown")
    cond_map = {c["type"]: c["status"] for c in pod["status"].get("conditions", [])}
    ready    = cond_map.get("Ready", "False")

    # container statuses
    restarts   = 0
    last_state = ""
    for cs in pod["status"].get("containerStatuses", []):
        restarts += cs.get("restartCount", 0)
        ls = cs.get("lastState", {})
        if "terminated" in ls:
            reason = ls["terminated"].get("reason", "")
            if reason:
                last_state = reason   # e.g. OOMKilled, Error

    # override phase for crash states
    for cs in pod["status"].get("containerStatuses", []):
        st = cs.get("state", {})
        if "waiting" in st:
            phase = st["waiting"].get("reason", phase)  # CrashLoopBackOff etc

    # skip if not errors-only
    if args.errors_only and phase == "Running" and restarts == 0:
        continue

    # requests / limits (first container)
    containers = pod["spec"].get("containers", [])
    cpu_req = cpu_lim = mem_req = mem_lim = "none"
    if containers:
        res = containers[0].get("resources", {})
        cpu_req = res.get("requests", {}).get("cpu", "none")
        cpu_lim = res.get("limits",   {}).get("cpu", "none")
        mem_req = res.get("requests", {}).get("memory", "none")
        mem_lim = res.get("limits",   {}).get("memory", "none")

    # actual usage from top
    tkey = f"{ns}/{name}" if not args.namespace else name
    top  = top_map.get(tkey, {})
    cpu_act = top.get("cpu", "N/A")
    mem_act = top.get("mem", "N/A")

    # warnings
    pkey    = f"{ns}/{name}"
    warns   = warn_map.get(pkey, [])
    if last_state:
        warns = [f"LastState={last_state}"] + warns
    warn_str = warns[0] if warns else ""

    # color coding in status
    status_display = phase
    if phase not in ("Running", "Succeeded", "Completed"):
        status_display = f"!{phase}"

    print(f"{ns:<20} {name:<55} {status_display:<12} {ready:<7} {restarts:>8}  "
          f"{cpu_act:>8} {cpu_req:>9} {cpu_lim:>9}   {mem_act:>9} {mem_req:>9} {mem_lim:>9}  {warn_str}")

    # print additional warnings on next lines
    for w in warns[1:3]:
        print(f"{'':>115}  {w}")

    found += 1

print("=" * 170)
print(f"Total pods shown: {found}")
