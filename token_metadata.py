"""
Token metadata fetched from Jupiter's public token list.
Covers virtually every SPL token — symbol, full name, and logo URL.
Results are cached locally for 24 hours so the app stays fast.
"""

import json
import os
import time

import requests

JUPITER_TOKEN_LIST_URL = "https://token.jup.ag/all"
CACHE_FILE = os.path.join(os.path.dirname(__file__), ".token_cache.json")
CACHE_TTL = 86_400  # 24 hours

# In-memory cache so we only hit disk once per process
_mem_cache: dict | None = None


def _load_cache() -> dict:
    global _mem_cache
    if _mem_cache is not None:
        return _mem_cache

    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE) as f:
                data = json.load(f)
            if time.time() - data.get("fetched_at", 0) < CACHE_TTL:
                _mem_cache = data["tokens"]
                return _mem_cache
        except (json.JSONDecodeError, KeyError):
            pass  # stale or corrupt — re-fetch

    return {}


def _save_cache(tokens: dict) -> None:
    global _mem_cache
    _mem_cache = tokens
    with open(CACHE_FILE, "w") as f:
        json.dump({"fetched_at": time.time(), "tokens": tokens}, f)


def fetch_token_list() -> dict:
    """
    Return the full Jupiter token list as a dict keyed by mint address:
        { mint: { symbol, name, logo_uri, decimals } }
    Fetches from the network only when the local cache is missing or stale.
    Returns an empty dict (never raises) so a metadata failure never
    blocks balance fetching.
    """
    cached = _load_cache()
    if cached:
        return cached

    try:
        resp = requests.get(JUPITER_TOKEN_LIST_URL, timeout=30)
        resp.raise_for_status()

        tokens: dict = {}
        for token in resp.json():
            mint = token.get("address")
            if mint:
                tokens[mint] = {
                    "symbol":   token.get("symbol", ""),
                    "name":     token.get("name", ""),
                    "logo_uri": token.get("logoURI") or "",
                    "decimals": token.get("decimals", 0),
                }

        _save_cache(tokens)
        return tokens
    except Exception:
        # Metadata is best-effort — balances still show with fallback labels
        return {}


def get_token_info(mint: str) -> dict:
    """
    Look up metadata for a single mint address.
    Falls back to a minimal dict if the token isn't in the list.
    """
    tokens = fetch_token_list()
    return tokens.get(mint) or {
        "symbol":   mint[:6] + "...",
        "name":     "Unknown Token",
        "logo_uri": "",
        "decimals": 0,
    }
