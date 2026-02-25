"""
Token metadata resolved from three sources in priority order:

1. Jupiter token list  — covers most liquid/traded tokens
2. Solana Labs token list — the original community registry, catches many
   tokens Jupiter's filters exclude (e.g. wrapped assets, older coins)
3. Helius getAsset (DAS) — queries on-chain Metaplex metadata directly;
   works for any token that has on-chain metadata, requires a free
   Helius API key set in config.yaml

Results from sources 1+2 are merged and cached locally for 24 hours.
"""

import json
import os
import time

import requests

JUPITER_TOKEN_LIST_URL = "https://token.jup.ag/all"
SOLANA_TOKEN_LIST_URL  = "https://raw.githubusercontent.com/solana-labs/token-list/main/src/tokens/solana.tokenlist.json"

CACHE_FILE = os.path.join(os.path.dirname(__file__), ".token_cache.json")
CACHE_TTL  = 86_400  # 24 hours

_mem_cache: dict | None = None


# ── Cache helpers ──────────────────────────────────────────────────────────

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
            pass

    return {}


def _save_cache(tokens: dict) -> None:
    global _mem_cache
    _mem_cache = tokens
    with open(CACHE_FILE, "w") as f:
        json.dump({"fetched_at": time.time(), "tokens": tokens}, f)


# ── Source fetchers ────────────────────────────────────────────────────────

def _fetch_solana_labs_list() -> dict:
    """Fetch the original Solana Labs community token registry."""
    try:
        resp = requests.get(SOLANA_TOKEN_LIST_URL, timeout=30)
        resp.raise_for_status()
        tokens: dict = {}
        for token in resp.json().get("tokens", []):
            if token.get("chainId") != 101:  # mainnet only
                continue
            mint = token.get("address")
            if mint:
                tokens[mint] = {
                    "symbol":   token.get("symbol", ""),
                    "name":     token.get("name", ""),
                    "logo_uri": token.get("logoURI") or "",
                    "decimals": token.get("decimals", 0),
                }
        return tokens
    except Exception:
        return {}


def _fetch_jupiter_list() -> dict:
    """Fetch Jupiter's token list (liquid/traded tokens)."""
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
        return tokens
    except Exception:
        return {}


def fetch_token_list() -> dict:
    """
    Return the merged token list (Solana Labs + Jupiter) keyed by mint address.
    Jupiter entries take precedence for duplicates (more up-to-date metadata).
    Cached locally for 24 hours.
    """
    cached = _load_cache()
    if cached:
        return cached

    # Fetch both — Jupiter wins on conflict
    merged = {**_fetch_solana_labs_list(), **_fetch_jupiter_list()}

    if merged:
        _save_cache(merged)

    return merged


# ── Helius on-chain fallback ───────────────────────────────────────────────

def _get_token_info_helius(mint: str, api_key: str) -> dict | None:
    """
    Fetch token metadata from Helius DAS API (getAsset).
    Queries on-chain Metaplex metadata — works for any token with metadata,
    regardless of whether it's in any off-chain list.
    Returns None on failure or missing metadata.
    """
    try:
        resp = requests.post(
            f"https://mainnet.helius-rpc.com/?api-key={api_key}",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getAsset",
                "params": {"id": mint},
            },
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json().get("result") or {}
        content  = result.get("content") or {}
        metadata = content.get("metadata") or {}
        links    = content.get("links") or {}
        token_info = result.get("token_info") or {}

        name     = metadata.get("name", "").strip()
        symbol   = metadata.get("symbol", "").strip()
        logo_uri = links.get("image", "")

        if name or symbol:
            return {
                "symbol":   symbol or mint[:6] + "...",
                "name":     name,
                "logo_uri": logo_uri,
                "decimals": token_info.get("decimals", 0),
            }
    except Exception:
        pass
    return None


# ── Public API ─────────────────────────────────────────────────────────────

def get_token_info(mint: str, helius_api_key: str = "") -> dict:
    """
    Look up metadata for a single mint address.

    Resolution order:
      1. Merged Jupiter + Solana Labs list (cached)
      2. Helius getAsset (on-chain Metaplex) if helius_api_key is set
      3. Short address fallback
    """
    tokens = fetch_token_list()
    if mint in tokens:
        return tokens[mint]

    if helius_api_key:
        info = _get_token_info_helius(mint, helius_api_key)
        if info:
            return info

    return {
        "symbol":   mint[:6] + "...",
        "name":     "Unknown Token",
        "logo_uri": "",
        "decimals": 0,
    }
