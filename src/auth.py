"""Minimal GMI Cloud auth shim.

The original project reads keys from a private ledger module; for this public
repository the key comes from the environment instead.

    export GMI_API_KEY=sk-...
"""
import os


def get_key():
    k = os.environ.get("GMI_API_KEY")
    if not k:
        raise SystemExit("GMI_API_KEY is not set")
    return k, "env"
