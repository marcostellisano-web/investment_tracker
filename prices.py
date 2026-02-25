"""
USD price fetching for Solana tokens via DexScreener.
Free, no API key required, covers all actively-traded SPL tokens including
Portal/Wormhole-wrapped assets that have on-chain Solana DEX liquidity.

Uses the v1 tokens endpoint (more reliable than the legacy /latest/dex/tokens
batch format which can silently drop results).
"""

import requests

# Newer, more reliable endpoint — one request per mint, Solana-scoped
DEXSCREENER_V1_URL = "https://api.dexscreener.com/tokens/v1/solana/{}"
_CHUNK_SIZE = 30  # v1 endpoint supports up to 30 comma-separated addresses

COINGECKO_SIMPLE_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"

LIVE_PRICE_IDS = {
    "SOL": "solana",
    "hSOL": "helius-staked-sol",
    "jitoSOL": "jito-staked-sol",
    "ZEC": "zcash",
    "HYPE": "hyperliquid",
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDC": "usd-coin",
}


def get_usd_prices(mints: list[str]) -> dict[str, float]:
    """
    Return { mint: usd_price } for the given mint addresses.

    Uses DexScreener tokens/v1 — picks the pair with the highest USD liquidity
    for each token to avoid thin/manipulated markets.
    """
    if not mints:
        return {}

    prices: dict[str, float] = {}

    for i in range(0, len(mints), _CHUNK_SIZE):
        chunk = mints[i : i + _CHUNK_SIZE]
        try:
            resp = requests.get(
                DEXSCREENER_V1_URL.format(",".join(chunk)),
                timeout=10,
            )
            resp.raise_for_status()
            body = resp.json()
            # v1 returns a top-level list; fall back to "pairs" key for safety
            pairs = body if isinstance(body, list) else (body.get("pairs") or [])

            best: dict[str, dict] = {}
            for pair in pairs:
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

    return prices


def get_live_watch_prices() -> dict[str, float | None]:
    """Return USD prices for the static live-price watchlist."""
    ids = list(LIVE_PRICE_IDS.values())
    prices_by_id: dict[str, float | None] = {token_id: None for token_id in ids}

    try:
        resp = requests.get(
            COINGECKO_SIMPLE_PRICE_URL,
            params={"ids": ",".join(ids), "vs_currencies": "usd"},
            timeout=10,
        )
        resp.raise_for_status()
        body = resp.json()
        for token_id in ids:
            price = (body.get(token_id) or {}).get("usd")
            prices_by_id[token_id] = float(price) if price is not None else None
    except Exception:
        pass

    return {
        symbol: prices_by_id.get(token_id)
        for symbol, token_id in LIVE_PRICE_IDS.items()
    }
