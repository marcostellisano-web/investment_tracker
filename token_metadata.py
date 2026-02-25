"""
Token metadata resolved from two sources:

  With Helius API key (recommended):
    1. Helius getAsset (on-chain Metaplex) — covers every SPL token
    2. Jupiter + Solana Labs merged list — fast cache fallback

  Without Helius key:
    1. Jupiter + Solana Labs merged list only

Results are cached in memory per-process. The bulk list is also cached
to disk (falls back to /tmp if the app directory is read-only).
"""

import json
import os
import tempfile
import time

import requests

JUPITER_TOKEN_LIST_URL = "https://token.jup.ag/all"
SOLANA_TOKEN_LIST_URL  = "https://raw.githubusercontent.com/solana-labs/token-list/main/src/tokens/solana.tokenlist.json"
CACHE_TTL = 86_400  # 24 hours

# ── Manual overrides ───────────────────────────────────────────────────────
# Tokens absent from all public lists (e.g. bridged/wrapped assets).
# These are checked FIRST and always win. Add new entries here as needed.
KNOWN_TOKENS: dict[str, dict] = {
    # Zcash — Portal (Wormhole) wrapped ZEC on Solana
    "A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS": {
        "symbol":   "ZEC",
        "name":     "Zcash (Portal)",
        "logo_uri": "https://coin-images.coingecko.com/coins/images/486/small/circle-zcash-color.png?1696501740",
        "decimals": 8,
    },
}

_mem_cache: dict | None = None          # merged Jupiter + Solana Labs list
_helius_mem_cache: dict = {}            # per-token Helius results (this process)


# ── Cache path (writable location) ────────────────────────────────────────

def _cache_path() -> str:
    """Return a writable path for the bulk token list cache."""
    app_dir = os.path.dirname(os.path.abspath(__file__))
    if os.access(app_dir, os.W_OK):
        return os.path.join(app_dir, ".token_cache.json")
    # Fall back to system temp directory (always writable)
    return os.path.join(tempfile.gettempdir(), "solana_token_cache.json")


# ── Disk cache helpers ─────────────────────────────────────────────────────

def _load_cache() -> dict:
    global _mem_cache
    if _mem_cache is not None:
        return _mem_cache

    path = _cache_path()
    if os.path.exists(path):
        try:
            with open(path) as f:
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
    try:
        with open(_cache_path(), "w") as f:
            json.dump({"fetched_at": time.time(), "tokens": tokens}, f)
    except OSError:
        pass  # If we still can't write, just keep the in-memory cache


# ── Bulk list fetchers ─────────────────────────────────────────────────────

def _fetch_solana_labs_list() -> dict:
    try:
        resp = requests.get(SOLANA_TOKEN_LIST_URL, timeout=30)
        resp.raise_for_status()
        tokens: dict = {}
        for token in resp.json().get("tokens", []):
            if token.get("chainId") != 101:
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
    """Return the merged Jupiter + Solana Labs list (cached to disk/tmp)."""
    cached = _load_cache()
    if cached:
        return cached

    merged = {**_fetch_solana_labs_list(), **_fetch_jupiter_list()}
    if merged:
        _save_cache(merged)
    return merged


# ── Helius per-token lookup ────────────────────────────────────────────────

def _get_token_info_helius(mint: str, api_key: str) -> dict | None:
    """
    Fetch on-chain Metaplex metadata via Helius DAS getAsset.
    Covers every SPL token that has on-chain metadata.
    Results are kept in _helius_mem_cache for the life of the process.
    """
    if mint in _helius_mem_cache:
        return _helius_mem_cache[mint]

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
        result     = resp.json().get("result") or {}
        content    = result.get("content") or {}
        metadata   = content.get("metadata") or {}
        links      = content.get("links") or {}
        token_info = result.get("token_info") or {}

        name     = metadata.get("name", "").strip()
        symbol   = metadata.get("symbol", "").strip()
        logo_uri = links.get("image", "")

        if name or symbol:
            info = {
                "symbol":   symbol or mint[:6] + "...",
                "name":     name,
                "logo_uri": logo_uri,
                "decimals": token_info.get("decimals", 0),
            }
            _helius_mem_cache[mint] = info
            return info
    except Exception:
        pass
    return None


# ── Public API ─────────────────────────────────────────────────────────────

def get_token_info(mint: str, helius_api_key: str = "") -> dict:
    """
    Look up metadata for a single mint address.

    Priority:
      1. KNOWN_TOKENS override dict   (hardcoded, always wins)
      2. Helius getAsset              (when key is set)
      3. Jupiter + Solana Labs list   (cached bulk fallback)
    """
    # 1. Manual overrides always win
    if mint in KNOWN_TOKENS:
        return KNOWN_TOKENS[mint]

    # 2. Helius first when key is set — it covers every token
    if helius_api_key:
        info = _get_token_info_helius(mint, helius_api_key)
        if info:
            return info

    # Bulk list fallback (or primary when no Helius key)
    tokens = fetch_token_list()
    if mint in tokens:
        return tokens[mint]

    return {
        "symbol":   mint[:6] + "...",
        "name":     "Unknown Token",
        "logo_uri": "",
        "decimals": 0,
    }
