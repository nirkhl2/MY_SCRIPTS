#!/usr/bin/env python3
"""
umbrella_monthly_report.py — generate MM_YYYY.json for one calendar month
from the Umbrella Cost (umbrellacost.io / formerly Anodot Cloud Cost) API.

Usage:
    # Discover the schema first (recommended on first run)
    python umbrella_monthly_report.py --discover
    python umbrella_monthly_report.py --discover --month 2026-01

    # Generate the report
    python umbrella_monthly_report.py            # last completed month
    python umbrella_monthly_report.py 2026-01    # specific month

Required env vars (pick ONE auth path):
    A) UMBRELLA_USERNAME + UMBRELLA_PASSWORD       (tokenizer login flow)
    B) UMBRELLA_API_KEY  + UMBRELLA_BEARER_TOKEN   (pre-issued from UI)

Always required:
    UMBRELLA_ACCOUNT_KEY            e.g. "11581"   (from UI URL accountKey=...)
    UMBRELLA_DIVISION_ID            e.g. "0"       (from UI URL divisionId=...)
    UMBRELLA_CLOUD_ACCOUNT_TYPE_ID  e.g. "0"       (0 = AWS payer; from UI URL)

Optional (override these only if --discover or DevTools shows a mismatch):
    UMBRELLA_BASE_URL               default https://api.umbrellacost.io/api/v1
    UMBRELLA_TOKENIZER_URL          default https://tokenizer.mypileus.io/prod/credentials
    UMBRELLA_COST_USAGE_PATH        default /usage/cost-and-usage
                                    (override if DevTools shows a different slug,
                                     e.g. /usage/data on some tenants)
    UMBRELLA_LINKED_ACCT_KEY        default linkedaccid
                                    (override to linkedaccountid / accountid if
                                     discovery shows your tenant uses that name)
    UMBRELLA_END_DATE_INCLUSIVE     default false (uses exclusive end like 2026-02-01)
                                    set "true" to use inclusive end like 2026-01-31
"""

from __future__ import annotations
import argparse
import calendar
import json
import os
import sys
import time
from datetime import date, timedelta
from typing import Any
import requests

# ---------------------------------------------------------------------------
# CONFIG: the four "named" linked accounts that get broken out individually.
# Edit display_key / account_name only — account_id is the AWS 12-digit ID.
# ---------------------------------------------------------------------------
NAMED_ACCOUNTS: dict[str, dict[str, str]] = {
    "prod-atlas":  {"account_name": "prod",        "account_id": "420848092533"},
    "dev-atlas":   {"account_name": "dev",         "account_id": "78779161144"},
    "dms-qa":      {"account_name": "rnd_driivz",  "account_id": "241560546024"},
    "management":  {"account_name": "driivz.com",  "account_id": "595691082268"},
}
NAMED_IDS: list[str] = [v["account_id"] for v in NAMED_ACCOUNTS.values()]

# Common chargetype labels — adjust if your tenant uses different strings.
# The --discover mode will print the actual labels seen in your tenant.
RI_CHARGETYPES = ["RIFee", "Recurring", "DiscountedUsage"]
SP_CHARGETYPES = ["SavingsPlanCoveredUsage", "SavingsPlanRecurringFee", "SavingsPlanNegation"]
CREDIT_CHARGETYPES = ["Credit"]

BASE_URL        = os.environ.get("UMBRELLA_BASE_URL", "https://api.umbrellacost.io/api/v1")
TOKENIZER_URL   = os.environ.get("UMBRELLA_TOKENIZER_URL", "https://tokenizer.mypileus.io/prod/credentials")
COST_USAGE_PATH = os.environ.get("UMBRELLA_COST_USAGE_PATH", "/usage/cost-and-usage")
LINKED_ACCT_KEY = os.environ.get("UMBRELLA_LINKED_ACCT_KEY", "linkedaccid")
END_DATE_INCLUSIVE = os.environ.get("UMBRELLA_END_DATE_INCLUSIVE", "false").lower() == "true"


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def get_credentials() -> tuple[str, str]:
    """Return (apikey, bearer_token). Prefers pre-issued creds, falls back to login."""
    apikey = os.environ.get("UMBRELLA_API_KEY")
    bearer = os.environ.get("UMBRELLA_BEARER_TOKEN")
    if apikey and bearer:
        return apikey, bearer

    user = os.environ.get("UMBRELLA_USERNAME")
    pw = os.environ.get("UMBRELLA_PASSWORD")
    if not (user and pw):
        sys.exit("Set either UMBRELLA_API_KEY+UMBRELLA_BEARER_TOKEN, "
                 "or UMBRELLA_USERNAME+UMBRELLA_PASSWORD.")
    r = requests.post(TOKENIZER_URL,
                      json={"username": user, "password": pw},
                      timeout=30)
    r.raise_for_status()
    j = r.json()
    # Tokenizer returns: {"Authorization": "<jwt>", "apikey": "<key:divid>"}
    return j["apikey"], j["Authorization"]


# ---------------------------------------------------------------------------
# Cost & Usage POST helper
# ---------------------------------------------------------------------------
class UmbrellaClient:
    def __init__(self, verbose: bool = False) -> None:
        self.apikey, self.bearer = get_credentials()
        self.account_key   = os.environ.get("UMBRELLA_ACCOUNT_KEY", "")
        self.division_id   = int(os.environ.get("UMBRELLA_DIVISION_ID", "0"))
        self.cloud_acct_id = int(os.environ.get("UMBRELLA_CLOUD_ACCOUNT_TYPE_ID", "0"))
        self.verbose = verbose
        self.session = requests.Session()
        auth_value = self.bearer if self.bearer.lower().startswith("bearer ") else f"Bearer {self.bearer}"
        self.session.headers.update({
            "apikey":        self.apikey,
            "Authorization": auth_value,
            "Content-Type":  "application/json",
            # commonParams is required on data endpoints — controls private-pricing rebilling.
            "commonParams":  json.dumps({"isPpApplied": False}),
        })

    def cost_and_usage(self, *,
                       start: str, end: str,
                       group_by: str = "none",
                       cost_type: str = "netamortizedcost",
                       filters: dict[str, list[str]] | None = None,
                       exclude_filters: dict[str, list[str]] | None = None,
                       gran_level: str = "month",
                       include_others: bool = False) -> dict[str, Any]:
        """POST /usage/cost-and-usage (path overridable via UMBRELLA_COST_USAGE_PATH)."""
        body: dict[str, Any] = {
            "startDate":           start,
            "endDate":             end,
            "granLevel":           gran_level,
            "periodGranLevel":     gran_level,
            "groupBy":             group_by,
            "costType":            cost_type,
            "currCostType":        cost_type,
            "filters":             filters or {},
            "excludeFilters":      exclude_filters or {},
            "includeOthers":       include_others,
            "isPpApplied":         False,
            "isNetAmortize":       cost_type == "netamortizedcost",
            "isNetUnblended":      cost_type == "netunblendedcost",
            "isPublicCost":        cost_type == "publiccost",
            "accountKey":          self.account_key,
            "cloudAccountTypeId":  self.cloud_acct_id,
            "divisionId":          self.division_id,
        }
        url = BASE_URL.rstrip("/") + COST_USAGE_PATH
        if self.verbose:
            print(f"\n>>> POST {url}")
            print(f">>> body: {json.dumps(body, indent=2)}")
        r = self.session.post(url, json=body, timeout=120)
        if self.verbose:
            print(f"<<< status: {r.status_code}")
            print(f"<<< body (first 2000 chars): {r.text[:2000]}")
        if r.status_code == 401:
            sys.exit(f"401 Unauthorized — JWT likely expired (24h). Re-issue and retry.\n{r.text}")
        if not r.ok:
            sys.exit(f"{r.status_code} from {url}\nbody={json.dumps(body)}\nresp={r.text[:1000]}")
        time.sleep(0.25)   # gentle pacing; no public rate-limit doc
        return r.json()


# ---------------------------------------------------------------------------
# Helpers to crunch responses
# ---------------------------------------------------------------------------
def _rows(j: Any) -> list[dict[str, Any]]:
    """Normalize: response is either {data:[...]} or a list."""
    if isinstance(j, list):
        return j
    if isinstance(j, dict):
        return j.get("data") or j.get("rows") or []
    return []


def _row_total(r: dict[str, Any]) -> float:
    for k in ("total_cost", "totalCost", "cost", "value"):
        if k in r and r[k] is not None:
            try:
                return float(r[k])
            except (TypeError, ValueError):
                pass
    return 0.0


def _row_group(r: dict[str, Any]) -> str:
    for k in ("groupBy", "group_by", "key", "name"):
        if k in r and r[k] is not None:
            return str(r[k])
    return ""


def _sum(j: Any) -> float:
    if isinstance(j, dict) and "totalCost" in j:
        try:
            return float(j["totalCost"])
        except (TypeError, ValueError):
            pass
    return sum(_row_total(r) for r in _rows(j))


def _to_int_dollars(x: float) -> int:
    return int(round(x))


def month_range(yyyy_mm: str) -> tuple[str, str]:
    y, m = map(int, yyyy_mm.split("-"))
    last = calendar.monthrange(y, m)[1]
    start = f"{y:04d}-{m:02d}-01"
    if END_DATE_INCLUSIVE:
        end = f"{y:04d}-{m:02d}-{last:02d}"
    else:
        next_m = date(y, m, last) + timedelta(days=1)
        end = next_m.strftime("%Y-%m-%d")
    return start, end


# ---------------------------------------------------------------------------
# DISCOVERY MODE: probe the API, print field names + sample values
# ---------------------------------------------------------------------------
def discover(month: str) -> None:
    """
    Run a few exploratory calls and print exactly what the API returns.
    Use this before trusting the report numbers — it will tell you:
      - whether the endpoint path works
      - what the response field names are (groupBy vs group_by, total_cost vs cost)
      - what chargetype labels your tenant uses (so you can edit RI/SP/CREDIT lists)
      - whether your linked-account dimension key is correct
    """
    start, end = month_range(month)
    cli = UmbrellaClient(verbose=True)

    print("=" * 78)
    print(f"DISCOVERY for month {month} ({start} -> {end})")
    print(f"  BASE_URL              = {BASE_URL}")
    print(f"  COST_USAGE_PATH       = {COST_USAGE_PATH}")
    print(f"  LINKED_ACCT_KEY       = {LINKED_ACCT_KEY}")
    print(f"  END_DATE_INCLUSIVE    = {END_DATE_INCLUSIVE}")
    print(f"  ACCOUNT_KEY           = {cli.account_key}")
    print(f"  DIVISION_ID           = {cli.division_id}")
    print(f"  CLOUD_ACCOUNT_TYPE_ID = {cli.cloud_acct_id}")
    print("=" * 78)

    # -----------------------------------------------------------------------
    # Probe 1: simplest possible call — total cost, no group, no filters
    # -----------------------------------------------------------------------
    print("\n[1/4] Probe: total cost (groupBy=none, costType=cost, no filters)")
    print("      Goal: confirm the endpoint path and auth work.")
    j1 = cli.cost_and_usage(
        start=start, end=end,
        group_by="none", cost_type="cost")
    rows1 = _rows(j1)
    print(f"      → response has {len(rows1)} rows; total = {_sum(j1):.2f}")
    if rows1:
        print(f"      → first row keys: {sorted(rows1[0].keys())}")
        print(f"      → first row sample: {json.dumps(rows1[0], indent=2)[:500]}")

    # -----------------------------------------------------------------------
    # Probe 2: groupBy chargetype — discover the chargetype labels
    # -----------------------------------------------------------------------
    print("\n[2/4] Probe: groupBy=chargetype (discover discount/credit labels)")
    print("      Goal: see which chargetype strings your tenant uses, so you can")
    print("            update RI_CHARGETYPES / SP_CHARGETYPES / CREDIT_CHARGETYPES.")
    j2 = cli.cost_and_usage(
        start=start, end=end,
        group_by="chargetype", cost_type="amortizedcost")
    rows2 = _rows(j2)
    print(f"      → got {len(rows2)} chargetype rows:")
    for r in sorted(rows2, key=_row_total, reverse=True):
        print(f"          {_row_group(r):<40s}  {_row_total(r):>14.2f}")

    # -----------------------------------------------------------------------
    # Probe 3: groupBy linked account — discover the account-dimension key
    # -----------------------------------------------------------------------
    print(f"\n[3/4] Probe: groupBy={LINKED_ACCT_KEY!r} (discover linked-account key)")
    print("      Goal: confirm that the linked-account dimension name is correct,")
    print("            and see how account_id / account_name come back per row.")
    try:
        j3 = cli.cost_and_usage(
            start=start, end=end,
            group_by=LINKED_ACCT_KEY, cost_type="netamortizedcost")
        rows3 = _rows(j3)
        print(f"      → got {len(rows3)} account rows.")
        if rows3:
            top5 = sorted(rows3, key=_row_total, reverse=True)[:5]
            print("      → top 5 accounts by spend:")
            for r in top5:
                print(f"          {_row_group(r):<40s}  {_row_total(r):>14.2f}")
            print(f"      → first row full payload:")
            print(f"        {json.dumps(top5[0], indent=2)[:800]}")
    except SystemExit as e:
        print(f"      ✗ FAILED with current key {LINKED_ACCT_KEY!r}.")
        print(f"        Try setting UMBRELLA_LINKED_ACCT_KEY to one of:")
        print(f"        linkedaccountid, accountid, payeraccount")
        print(f"        Original error: {e}")

    # -----------------------------------------------------------------------
    # Probe 4: filter a single named account → groupBy service
    # -----------------------------------------------------------------------
    test_acct = NAMED_IDS[0]
    print(f"\n[4/4] Probe: services for one named account ({test_acct})")
    print("      Goal: confirm the include-filter shape works for a single account.")
    try:
        j4 = cli.cost_and_usage(
            start=start, end=end,
            group_by="service", cost_type="netamortizedcost",
            filters={LINKED_ACCT_KEY: [test_acct]},
            exclude_filters={"chargetype": ["Tax"]})
        rows4 = _rows(j4)
        print(f"      → got {len(rows4)} service rows for account {test_acct}; "
              f"total = {_sum(j4):.2f}")
        for r in sorted(rows4, key=_row_total, reverse=True)[:10]:
            print(f"          {_row_group(r):<40s}  {_row_total(r):>14.2f}")
    except SystemExit as e:
        print(f"      ✗ FAILED. Check the filter key name. Error: {e}")

    print("\n" + "=" * 78)
    print("DISCOVERY COMPLETE")
    print("=" * 78)
    print("""
Next steps:
  1. If any probe failed with 404 → wrong path. Open umbrellacost.io → DevTools
     → Network → XHR, click any filter in Cost & Usage Explorer, copy the request
     URL, and set:    export UMBRELLA_COST_USAGE_PATH=/usage/<the slug you saw>

  2. If probe 3 failed but probe 1 worked → wrong dimension name. Try:
        export UMBRELLA_LINKED_ACCT_KEY=linkedaccountid
        export UMBRELLA_LINKED_ACCT_KEY=accountid

  3. If the chargetype labels in probe 2 differ from RI_CHARGETYPES /
     SP_CHARGETYPES / CREDIT_CHARGETYPES at the top of this file, edit those
     lists to match what your tenant actually returns.

  4. If probe 1 returns 0 rows or a suspiciously small total, the date range may
     be off-by-one. Try toggling:
        export UMBRELLA_END_DATE_INCLUSIVE=true

  5. Once all four probes look correct, run without --discover to generate the
     monthly JSON.
""")


# ---------------------------------------------------------------------------
# Build the report
# ---------------------------------------------------------------------------
def build_report(month: str) -> dict[str, Any]:
    start, end = month_range(month)
    cli = UmbrellaClient()

    # =========================================================================
    # GENERAL — total cost rollups for the month
    # UI equivalent: "Cost & Usage Explorer" total tile, groupBy=costtype, no filters.
    # =========================================================================

    # (a) total_costs_no_discounts  →  costType=publiccost (list / on-demand price)
    no_disc = _sum(cli.cost_and_usage(
        start=start, end=end, group_by="none", cost_type="publiccost",
        exclude_filters={"chargetype": ["Tax", "Credit", "Refund"]}))

    # (b) total_costs_after_discounts  →  costType=netamortizedcost
    net = _sum(cli.cost_and_usage(
        start=start, end=end, group_by="none", cost_type="netamortizedcost",
        exclude_filters={"chargetype": ["Tax"]}))

    # (c) discount breakdown via groupBy=chargetype
    by_charge = cli.cost_and_usage(
        start=start, end=end, group_by="chargetype", cost_type="amortizedcost")
    charge_rows = {_row_group(r): _row_total(r) for r in _rows(by_charge)}

    ri_disc = sum(v for k, v in charge_rows.items() if k in RI_CHARGETYPES)
    sp_disc = sum(v for k, v in charge_rows.items() if k in SP_CHARGETYPES)
    credits = abs(sum(v for k, v in charge_rows.items() if k in CREDIT_CHARGETYPES))

    # Prefer costType=savingscost numbers if available — they give the actual
    # dollar discount delta (vs list price) per chargetype.
    sav = cli.cost_and_usage(
        start=start, end=end, group_by="chargetype", cost_type="savingscost")
    sav_rows = {_row_group(r): _row_total(r) for r in _rows(sav)}
    ri_disc_savings = sum(v for k, v in sav_rows.items() if k in RI_CHARGETYPES)
    sp_disc_savings = sum(v for k, v in sav_rows.items() if k in SP_CHARGETYPES)
    ri_disc = ri_disc_savings or ri_disc
    sp_disc = sp_disc_savings or sp_disc

    general = {
        "total_costs_after_discounts":  _to_int_dollars(net),
        "total_costs_no_discounts":     _to_int_dollars(no_disc),
        "total_discounts":              _to_int_dollars(no_disc - net),
        "reserved_instances_discount":  _to_int_dollars(ri_disc),
        "savings_plan_discount":        _to_int_dollars(sp_disc),
        "credits_usage":                _to_int_dollars(credits),
    }

    # =========================================================================
    # ACCOUNTS — one block per named account, plus the dms-ops aggregate
    # =========================================================================
    accounts: dict[str, Any] = {}

    # (d) Per-named-account: total + services breakdown
    for key, meta in NAMED_ACCOUNTS.items():
        aid = meta["account_id"]
        j = cli.cost_and_usage(
            start=start, end=end, group_by="service", cost_type="netamortizedcost",
            filters={LINKED_ACCT_KEY: [aid]},
            exclude_filters={"chargetype": ["Tax"]})
        services = {_row_group(r): _to_int_dollars(_row_total(r)) for r in _rows(j)}
        # drop zero/empty rows
        services = {k: v for k, v in services.items() if k and v}
        accounts[key] = {
            "account_name": meta["account_name"],
            "account_id":   aid,
            "total":        _to_int_dollars(sum(services.values())),
            "services":     services,
        }

    # (e) dms-ops: everything EXCEPT the four named accounts
    others = cli.cost_and_usage(
        start=start, end=end, group_by=LINKED_ACCT_KEY, cost_type="netamortizedcost",
        exclude_filters={LINKED_ACCT_KEY: NAMED_IDS, "chargetype": ["Tax"]})
    other_rows = _rows(others)

    def _row_id(r):
        return r.get("account_id") or _row_group(r)

    def _row_name(r):
        return r.get("account_name") or r.get("linkedAccountName") or _row_id(r)

    other_total = sum(_row_total(r) for r in other_rows)
    top5_rows = sorted(other_rows, key=_row_total, reverse=True)[:5]

    top5: dict[str, Any] = {}
    for r in top5_rows:
        rid = _row_id(r)
        rname = _row_name(r)
        # Drill-down: services for this single account
        svc = cli.cost_and_usage(
            start=start, end=end, group_by="service", cost_type="netamortizedcost",
            filters={LINKED_ACCT_KEY: [rid]},
            exclude_filters={"chargetype": ["Tax"]})
        services = {_row_group(s): _to_int_dollars(_row_total(s)) for s in _rows(svc)}
        services = {k: v for k, v in services.items() if k and v}
        top5[rname] = {
            "account_id":   rid,
            "account_name": rname,
            "total":        _to_int_dollars(_row_total(r)),
            "services":     services,
        }

    accounts["dms-ops"] = {
        "total":          _to_int_dollars(other_total),
        "total_accounts": len(other_rows),
        "top_5_accounts": top5,
    }

    return {"general": general, "accounts": accounts}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def last_completed_month() -> str:
    today = date.today().replace(day=1)
    prev = today - timedelta(days=1)
    return prev.strftime("%Y-%m")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("month_pos", nargs="?", default=None,
                    help="YYYY-MM (default: last completed month)")
    ap.add_argument("--month", dest="month_flag", default=None,
                    help="YYYY-MM (alternative to positional arg)")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--discover", action="store_true",
                    help="Run discovery probes against the API and print results "
                         "(use this on first run to verify the schema).")
    args = ap.parse_args()

    month = args.month_flag or args.month_pos or last_completed_month()

    if args.discover:
        discover(month)
        return

    report = build_report(month)
    y, m = month.split("-")
    fname = os.path.join(args.out_dir, f"{int(m):02d}_{int(y):04d}.json")
    with open(fname, "w") as f:
        json.dump(report, f, indent=2, sort_keys=False)
    print(f"wrote {fname}")


if __name__ == "__main__":
    main()
