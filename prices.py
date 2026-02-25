"""
USD price fetching for Solana tokens.

Primary source: DexScreener (free, no key, covers actively-traded SPL tokens).
Fallback:       CoinGecko simple price API (free, covers bridged/wrapped assets
                that have no on-chain Solana liquidity, e.g. Portal-wrapped ZEC).
"""

import requests

DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens/{}"
COINGECKO_URL   = "https://api.coingecko.com/api/v3/simple/price"
_CHUNK_SIZE = 30  # DexScreener handles ~30 addresses per request comfortably

# Mint → CoinGecko coin ID for tokens that don't trade on Solana DEXes
_COINGECKO_IDS: dict[str, str] = {
    "So11111111111111111111111111111111111111112":  "solana",   # SOL
    "A7bdiYdS5GjqGFtxf17ppRHtDKPkkRqbKtR27dxvQXaS": "zcash",  # ZEC (Portal/Wormhole)
}


def get_usd_prices(mints: list[str]) -> dict[str, float]:
    """
    Return { mint: usd_price } for the given mint addresses.

    1. Tries DexScreener for all mints (picks highest-liquidity pair).
    2. For any mints still missing a price that have a CoinGecko ID mapping,
       falls back to CoinGecko's simple price endpoint.
    """
    if not mints:
        return {}

    prices: dict[str, float] = {}

    # ── Step 1: DexScreener ──────────────────────────────────────────────────
    for i in range(0, len(mints), _CHUNK_SIZE):
        chunk = mints[i : i + _CHUNK_SIZE]
        try:
            resp = requests.get(
                DEXSCREENER_URL.format(",".join(chunk)),
                timeout=10,
            )
            resp.raise_for_status()
            pairs = resp.json().get("pairs") or []

            best: dict[str, dict] = {}
            for pair in pairs:
                if pair.get("chainId") != "solana":
                    continue
                addr = (pair.get("baseToken") or {}).get("address")
                price_str = pair.get("priceUsd")
                if not addr or not price_str:
                    continue
                liq = ((pair.get("liquidity") or {}).get("usd") or 0)
                if addr not in best or liq > best[addr]["liq"]:
                    best[addr] = {"price": float(price_str), "liq": liq}

            for addr, data in best.items():
                prices[addr] = data["price"]

        except Exception:
            pass

    # ── Step 2: CoinGecko fallback for mints still missing ───────────────────
    missing = [m for m in mints if m not in prices and m in _COINGECKO_IDS]
    if missing:
        cg_ids = list({_COINGECKO_IDS[m] for m in missing})
        try:
            resp = requests.get(
                COINGECKO_URL,
                params={"ids": ",".join(cg_ids), "vs_currencies": "usd"},
                timeout=10,
            )
            resp.raise_for_status()
            cg_data = resp.json()
            for mint in missing:
                cg_id = _COINGECKO_IDS[mint]
                usd = (cg_data.get(cg_id) or {}).get("usd")
                if usd is not None:
                    prices[mint] = float(usd)
        except Exception:
            pass

    return prices

