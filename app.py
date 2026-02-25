#!/usr/bin/env python3
"""
Solana Portfolio Tracker — Web UI
Run: python app.py  then open http://localhost:5000
"""

import json
import os

import yaml
from flask import Flask, jsonify, render_template, request

from solana import get_all_balances

app = Flask(__name__)
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")

SOL_MINT = "So11111111111111111111111111111111111111112"


def _load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def _save_config(wallets: list[dict]) -> None:
    cfg = _load_config()
    cfg["wallets"] = wallets
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)


def _rpc_url() -> str:
    return _load_config().get("rpc_url", "https://api.mainnet-beta.solana.com")


@app.route("/")
def index():
    """Serve the main page, pre-populating saved wallets if any."""
    cfg = _load_config()
    saved = [
        w for w in cfg.get("wallets", [])
        if not any(p in w.get("address", "") for p in ("YourFirst", "YourSecond", "YourThird"))
    ]
    return render_template("index.html", saved_wallets=saved)


@app.route("/api/saved-wallets")
def saved_wallets():
    cfg = _load_config()
    wallets = [
        w for w in cfg.get("wallets", [])
        if not any(p in w.get("address", "") for p in ("YourFirst", "YourSecond", "YourThird"))
    ]
    return jsonify(wallets)


@app.route("/api/fetch", methods=["POST"])
def fetch():
    """Fetch balances for submitted wallet addresses."""
    body = request.get_json(force=True)
    wallets = body.get("wallets", [])  # [{ address, label }]
    rpc_url = _rpc_url()

    results = []
    all_mints = {}  # mint -> symbol (for building column headers)

    for w in wallets:
        address = w.get("address", "").strip()
        label = w.get("label", "").strip() or address[:8] + "..."

        if not address:
            continue

        try:
            balances = get_all_balances(rpc_url, address)
            error = None
        except Exception as e:
            balances = {}
            error = str(e)

        for mint, data in balances.items():
            all_mints[mint] = data["symbol"]

        results.append({
            "label": label,
            "address": address,
            "balances": balances,
            "error": error,
        })

    # Build aggregated totals
    totals = {}
    for mint, symbol in all_mints.items():
        total = sum(r["balances"].get(mint, {}).get("amount", 0.0) for r in results)
        totals[mint] = {"symbol": symbol, "total": total}

    # Sort: SOL first, then by total descending
    sorted_mints = sorted(
        totals.keys(),
        key=lambda m: (0 if m == SOL_MINT else 1, -totals[m]["total"])
    )

    return jsonify({
        "wallets": results,
        "totals": totals,
        "sorted_mints": sorted_mints,
    })


@app.route("/api/save", methods=["POST"])
def save():
    """Persist wallet list to config.yaml."""
    body = request.get_json(force=True)
    wallets = body.get("wallets", [])
    _save_config([{"address": w["address"], "label": w.get("label", "")} for w in wallets])
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
