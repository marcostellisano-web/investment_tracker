"""
Solana RPC helpers — fetches SOL balance and all SPL token balances for a wallet.
"""

import requests

# Mint address -> human-readable symbol for common tokens.
# The tracker will still show unknown tokens by their mint address,
# but these get a nice symbol instead.
KNOWN_TOKENS = {
    "So11111111111111111111111111111111111111112":  "SOL",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
    "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij":  "cbBTC",
    "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh": "wBTC",
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs": "wETH",
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN":  "JUP",
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": "BONK",
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm": "WIF",
    "MEFNBXixkEbait3xn9bkm8WsJzXtVsaJEn4c8Sam21p":  "MEW",
    "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3": "PYTH",
    "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE":  "ORCA",
    "MNDEFzGvMt87ueuHvVU9VcTqsAP5b3fTGPsHuuPA5ey":  "MNDE",
    "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof":  "RENDER",
    "StepAscQoEioFxxWGnh2sLBDFp9d8rvKz2Yp39iDpyT":  "STEP",
}

SOL_MINT = "So11111111111111111111111111111111111111112"
LAMPORTS_PER_SOL = 1_000_000_000


def _rpc(rpc_url: str, method: str, params: list) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    response = requests.post(rpc_url, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise RuntimeError(f"RPC error: {data['error']}")
    return data["result"]


def get_sol_balance(rpc_url: str, address: str) -> float:
    """Return the native SOL balance for a wallet address."""
    result = _rpc(rpc_url, "getBalance", [address])
    return result["value"] / LAMPORTS_PER_SOL


def get_token_balances(rpc_url: str, address: str) -> dict[str, dict]:
    """
    Return all SPL token balances for a wallet.

    Returns a dict keyed by mint address:
        { mint: { "symbol": str, "amount": float, "decimals": int } }
    """
    result = _rpc(
        rpc_url,
        "getTokenAccountsByOwner",
        [
            address,
            {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
            {"encoding": "jsonParsed"},
        ],
    )

    balances = {}
    for account in result.get("value", []):
        info = account["account"]["data"]["parsed"]["info"]
        mint = info["mint"]
        decimals = info["tokenAmount"]["decimals"]
        amount = float(info["tokenAmount"]["uiAmountString"])

        if amount == 0:
            continue

        symbol = KNOWN_TOKENS.get(mint, mint[:6] + "...")
        balances[mint] = {
            "symbol": symbol,
            "amount": amount,
            "decimals": decimals,
        }

    return balances


def get_all_balances(rpc_url: str, address: str) -> dict[str, dict]:
    """
    Return native SOL + all SPL token balances for a wallet.
    SOL is included under its canonical mint address.
    """
    all_balances = {}

    sol = get_sol_balance(rpc_url, address)
    if sol > 0:
        all_balances[SOL_MINT] = {
            "symbol": "SOL",
            "amount": sol,
            "decimals": 9,
        }

    spl = get_token_balances(rpc_url, address)
    all_balances.update(spl)

    return all_balances
