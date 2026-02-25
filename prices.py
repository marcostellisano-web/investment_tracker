"""
USD price fetching for Solana tokens via DexScreener.
Free, no API key required, covers all traded SPL tokens.
"""

import requests

DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens/{}"
_CHUNK_SIZE = 30  # DexScreener handles ~30 addresses per request comfortably


def get_usd_prices(mints: list[str]) -> dict[str, float]:
    """
    Return { mint: usd_price } for the given mint addresses.

    Uses DexScreener — picks the pair with the highest USD liquidity for
    each token to avoid thin/manipulated markets. Tokens with no active
    trading pairs are simply omitted from the result.
    """
    if not mints:
        return {}

    prices: dict[str, float] = {}

    for i in range(0, len(mints), _CHUNK_SIZE):
        chunk = mints[i : i + _CHUNK_SIZE]
        try:
            resp = requests.get(
                DEXSCREENER_URL.format(",".join(chunk)),
                timeout=10,
            )
            resp.raise_for_status()
            pairs = resp.json().get("pairs") or []

            # For each mint keep the pair with the best (highest) liquidity
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
            pass  # Return whatever prices we have so far; don't crash

    return prices
