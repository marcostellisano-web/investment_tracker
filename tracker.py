#!/usr/bin/env python3
"""
Solana Portfolio Tracker
Aggregates token holdings across all wallets defined in config.yaml.

Usage:
    python tracker.py
"""

import sys
from collections import defaultdict

import yaml
from rich.console import Console
from rich.table import Table
from rich import box

from solana import get_all_balances

console = Console()


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def fetch_all_wallets(config: dict) -> tuple[list[dict], dict]:
    """
    Query every wallet and return:
      - wallet_results: list of { label, address, balances }
      - totals: { mint: { symbol, total_amount } }
    """
    rpc_url = config.get("rpc_url", "https://api.mainnet-beta.solana.com")
    wallets = config.get("wallets", [])

    wallet_results = []
    totals: dict[str, dict] = defaultdict(lambda: {"symbol": "", "total": 0.0})

    for wallet in wallets:
        address = wallet["address"]
        label = wallet.get("label", address[:8] + "...")

        console.print(f"  Fetching [cyan]{label}[/cyan] ({address[:8]}...)", end="")

        try:
            balances = get_all_balances(rpc_url, address)
            console.print(" [green]done[/green]")
        except Exception as e:
            console.print(f" [red]failed: {e}[/red]")
            balances = {}

        wallet_results.append({
            "label": label,
            "address": address,
            "balances": balances,
        })

        for mint, data in balances.items():
            totals[mint]["symbol"] = data["symbol"]
            totals[mint]["total"] += data["amount"]

    return wallet_results, dict(totals)


def print_summary(wallet_results: list[dict], totals: dict) -> None:
    """Print the aggregated portfolio table."""

    wallet_labels = [w["label"] for w in wallet_results]

    # Sort tokens: SOL first, then by total value descending
    SOL_MINT = "So11111111111111111111111111111111111111112"
    sorted_mints = sorted(
        totals.keys(),
        key=lambda m: (0 if m == SOL_MINT else 1, -totals[m]["total"])
    )

    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
        title="[bold]Solana Portfolio[/bold]",
        title_style="bold white",
    )

    table.add_column("Token", style="bold cyan", min_width=10)
    table.add_column("Total", justify="right", style="bold green", min_width=14)

    for label in wallet_labels:
        table.add_column(label, justify="right", min_width=14)

    for mint in sorted_mints:
        token_data = totals[mint]
        symbol = token_data["symbol"]
        total = token_data["total"]

        row = [symbol, _fmt(total)]

        for wallet in wallet_results:
            bal = wallet["balances"].get(mint, {}).get("amount", 0.0)
            row.append(_fmt(bal) if bal > 0 else "[dim]—[/dim]")

        table.add_row(*row)

    console.print()
    console.print(table)
    console.print(
        f"\n[dim]Tracked {len(wallet_labels)} wallet(s) · "
        f"{len(sorted_mints)} token(s) found[/dim]\n"
    )


def _fmt(amount: float) -> str:
    """Format a token amount nicely based on its magnitude."""
    if amount == 0:
        return "0"
    if amount >= 1_000:
        return f"{amount:,.2f}"
    if amount >= 1:
        return f"{amount:.4f}"
    if amount >= 0.0001:
        return f"{amount:.6f}"
    return f"{amount:.8f}"


def main():
    console.print("\n[bold white]Solana Portfolio Tracker[/bold white]")
    console.print("[dim]Loading config...[/dim]")

    try:
        config = load_config()
    except FileNotFoundError:
        console.print("[red]Error: config.yaml not found. Copy config.yaml and add your wallet addresses.[/red]")
        sys.exit(1)

    wallets = config.get("wallets", [])
    if not wallets:
        console.print("[yellow]No wallets configured. Add your addresses to config.yaml.[/yellow]")
        sys.exit(0)

    # Warn if user forgot to replace placeholder addresses
    placeholder_count = sum(1 for w in wallets if "YourFirst" in w["address"] or "YourSecond" in w["address"] or "YourThird" in w["address"])
    if placeholder_count == len(wallets):
        console.print("[yellow]It looks like you haven't added your wallet addresses yet.[/yellow]")
        console.print("[yellow]Edit config.yaml and replace the placeholder addresses.[/yellow]")
        sys.exit(0)

    console.print(f"[dim]Querying {len(wallets)} wallet(s)...[/dim]\n")

    wallet_results, totals = fetch_all_wallets(config)

    if not totals:
        console.print("[yellow]No token balances found across any wallet.[/yellow]")
        return

    print_summary(wallet_results, totals)


if __name__ == "__main__":
    main()
