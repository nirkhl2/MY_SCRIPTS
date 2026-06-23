#!/usr/bin/env python3
import subprocess, re, json

def run(cmd):
    return subprocess.check_output(cmd, shell=True).decode()

print("Fetching data...")
nodes_json = json.loads(run("kubectl get nodes -o json"))
pods_json  = json.loads(run("kubectl get pods --all-namespaces -o json"))
all_desc   = run("kubectl describe nodes")
top_out    = run("kubectl top nodes --no-headers")

# --- parse kubectl top nodes: actual cpu/mem usage ---
# format: NAME  CPU(cores)  CPU%  MEMORY(bytes)  MEMORY%
actual = {}
for line in top_out.strip().splitlines():
    parts = line.split()
    if len(parts) >= 5:
        actual[parts[0]] = {
            "cpu_cores": parts[1],   # e.g. 423m
            "cpu_pct":   parts[2],   # e.g. 10%
            "mem_bytes": parts[3],   # e.g. 4012Mi
            "mem_pct":   parts[4],   # e.g. 26%
        }

# --- pods per node ---
pod_count = {}
for pod in pods_json["items"]:
    n = pod.get("spec", {}).get("nodeName", "")
    if n:
        pod_count[n] = pod_count.get(n, 0) + 1

# --- split describe output into per-node blocks ---
desc_blocks = {}
for block in re.split(r'\nName:\s+', all_desc):
    if not block.strip():
        continue
    bname = block.split('\n')[0].strip()
    desc_blocks[bname] = block

# --- report ---
print("=" * 165)
print(f"{'NODE':<48} {'TYPE':<10} {'POOL / NODEGROUP':<22} {'PODS':>5}  "
      f"{'ACTUAL_CPU':>12} {'CPU_REQ(%)':>14} {'CPU_LIM(%)':>14}   {'ACTUAL_MEM':>12} {'MEM_REQ(%)':>16} {'MEM_LIM(%)':>16}")
print("=" * 165)

for node in nodes_json["items"]:
    name   = node["metadata"]["name"]
    labels = node["metadata"].get("labels", {})
    ng     = labels.get("eks.amazonaws.com/nodegroup", "")
    kp     = labels.get("karpenter.sh/nodepool", "")

    node_type  = "NodeGroup" if ng else "Karpenter"
    pool_label = ng[-22:] if ng else (kp if kp else "N/A")

    pods = pod_count.get(name, 0)

    cr = cl = mr = ml = "N/A"
    cpu_req_str = cpu_lim_str = mem_req_str = mem_lim_str = "N/A"
    block = desc_blocks.get(name, "")
    sec = re.search(r"Allocated resources:(.*?)(?=\nEvents:|\Z)", block, re.DOTALL)
    if sec:
        cm = re.search(r"cpu\s+(\S+)\s+\((\d+)%\)\s+(\S+)\s+\((\d+)%\)", sec.group(1))
        mm = re.search(r"memory\s+(\S+)\s+\((\d+)%\)\s+(\S+)\s+\((\d+)%\)", sec.group(1))
        if cm: cr, cpu_req_pct, cl, cpu_lim_pct = cm.group(1), cm.group(2), cm.group(3), cm.group(4)
        if mm: mr, mem_req_pct, ml, mem_lim_pct = mm.group(1), mm.group(2), mm.group(3), mm.group(4)
        cpu_req_str = f"{cr}({cpu_req_pct}%)" if cm else "N/A"
        cpu_lim_str = f"{cl}({cpu_lim_pct}%)" if cm else "N/A"
        mem_req_str = f"{mr}({mem_req_pct}%)" if mm else "N/A"
        mem_lim_str = f"{ml}({mem_lim_pct}%)" if mm else "N/A"

    top = actual.get(name, {})
    actual_cpu = f"{top['cpu_cores']}({top['cpu_pct']})" if top else "N/A"
    actual_mem = f"{top['mem_bytes']}({top['mem_pct']})" if top else "N/A"

    print(f"{name:<48} {node_type:<10} {pool_label:<22} {pods:>5}  "
          f"{actual_cpu:>12} {cpu_req_str:>14} {cpu_lim_str:>14}   {actual_mem:>12} {mem_req_str:>16} {mem_lim_str:>16}")

print("=" * 165)
