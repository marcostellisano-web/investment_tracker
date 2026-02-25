"""
Solana RPC helpers — fetches SOL balance and all SPL token balances for a wallet.
Token metadata (name, symbol, logo) is resolved from the Jupiter token list.
"""

import requests
from token_metadata import get_token_info

SOL_MINT = "So11111111111111111111111111111111111111112"
LAMPORTS_PER_SOL = 1_000_000_000

_SOL_META = {
    "symbol":   "SOL",
    "name":     "Solana",
    "logo_uri": "https://raw.githubusercontent.com/solana-labs/token-list/main/assets/mainnet/So11111111111111111111111111111111111111112/logo.png",
    "decimals": 9,
}


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


_TOKEN_PROGRAMS = [
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",   # Token Program (v1)
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",   # Token-2022 / Token Extensions
]


def get_token_balances(rpc_url: str, address: str) -> dict[str, dict]:
    """
    Return all SPL token balances for a wallet across both the original
    Token Program and Token-2022 (Token Extensions Program).

    Returns a dict keyed by mint address:
        { mint: { symbol, name, logo_uri, amount, decimals } }
    """
    balances = {}

    for program_id in _TOKEN_PROGRAMS:
        result = _rpc(
            rpc_url,
            "getTokenAccountsByOwner",
            [
                address,
                {"programId": program_id},
                {"encoding": "jsonParsed"},
            ],
        )

        for account in result.get("value", []):
            info = account["account"]["data"]["parsed"]["info"]
            mint = info["mint"]
            amount = float(info["tokenAmount"]["uiAmountString"])

            if amount == 0:
                continue

            meta = get_token_info(mint)
            balances[mint] = {
                "symbol":   meta["symbol"],
                "name":     meta["name"],
                "logo_uri": meta["logo_uri"],
                "amount":   amount,
                "decimals": meta["decimals"],
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
        all_balances[SOL_MINT] = {**_SOL_META, "amount": sol}

    spl = get_token_balances(rpc_url, address)
    all_balances.update(spl)

    return all_balances
