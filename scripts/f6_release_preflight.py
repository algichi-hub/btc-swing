#!/usr/bin/env python3
"""Offline G6 release preflight. No network, DB mutations, deploys or secrets read.

Supply an evidence JSON with explicit booleans. Absence is NO-GO by design.
Usage: python scripts/f6_release_preflight.py docs/F6_G6_EVIDENCE.json
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

REQUIRED=(
    "g3_midwrite_recovery","g4_authenticated_rbac","g4_logout_csrf",
    "g5_provider_retries","g5_android_resubscribe","telegram_removed",
    "full_regression","rollback_verified"
)

def evaluate(evidence: dict) -> tuple[bool,list[str]]:
    if not isinstance(evidence,dict):
        return False,["invalid_evidence"]
    missing=[]
    for k in REQUIRED:
        record=evidence.get(k)
        if not isinstance(record,dict) or record.get("status")!="PASS" or not record.get("evidence_url"):
            missing.append(k)
    return not missing,missing

def main(argv: list[str]) -> int:
    if len(argv)!=2:
        print("Usage: python scripts/f6_release_preflight.py evidence.json")
        return 2
    obj=json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    ok,missing=evaluate(obj)
    print("GO" if ok else "NO-GO")
    if missing: print("Missing documented evidence: "+", ".join(missing))
    return 0 if ok else 1

if __name__=="__main__":
    raise SystemExit(main(sys.argv))
