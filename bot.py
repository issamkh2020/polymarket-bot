#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║         POLYMARKET LATE-RESOLUTION ARBITRAGE BOT            ║
║              GitHub Actions Edition (Free 24/7)             ║
║                                                              ║
║  Two modes:                                                  ║
║    python bot.py          → scan & trade                     ║
║    python bot.py resolve  → check results + print P&L       ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import time
import logging
import requests
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
PRIVATE_KEY        = os.getenv("PRIVATE_KEY", "")
API_KEY            = os.getenv("CLOB_API_KEY", "")
API_SECRET         = os.getenv("CLOB_SECRET", "")
API_PASSPHRASE     = os.getenv("CLOB_PASSPHRASE", "")
TRADE_SIZE_USDC    = float(os.getenv("TRADE_SIZE_USDC", "5"))
MIN_PRICE          = float(os.getenv("MIN_PRICE", "0.90"))
MAX_PRICE          = float(os.getenv("MAX_PRICE", "0.97"))
MAX_HOURS_TO_CLOSE = int(os.getenv("MAX_HOURS_TO_CLOSE", "48"))
MIN_VOLUME_USDC    = float(os.getenv("MIN_VOLUME_USDC", "5000"))
DRY_RUN            = os.getenv("DRY_RUN", "true").lower() == "true"
DAILY_SPEND_CAP    = float(os.getenv("DAILY_SPEND_CAP", "10"))
MOMENTUM_DROP_PCT  = float(os.getenv("MOMENTUM_DROP_PCT", "2.0"))

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_HOST = "https://clob.polymarket.com"

PURCHASED_FILE   = "purchased.json"
POSITIONS_FILE   = "positions.json"
DAILY_SPEND_FILE = "daily_spend.json"
RESULTS_FILE     = "results.json"


# ══════════════════════════════════════════════════════════════
#  FILE HELPERS
# ══════════════════════════════════════════════════════════════

def load_purchased() -> set:
    if os.path.exists(PURCHASED_FILE):
        try:
            with open(PURCHASED_FILE, "r") as f:
                return set(json.load(f).get("purchased", []))
        except Exception:
            pass
    return set()


def save_purchased(purchased: set):
    with open(PURCHASED_FILE, "w") as f:
        json.dump({"purchased": list(purchased), "updated": str(datetime.now(timezone.utc))}, f, indent=2)


def load_positions() -> list:
    if os.path.exists(POSITIONS_FILE):
        try:
            with open(POSITIONS_FILE, "r") as f:
                return json.load(f).get("positions", [])
        except Exception:
            pass
    return []


def save_positions(positions: list):
    with open(POSITIONS_FILE, "w") as f:
        json.dump({"positions": positions, "updated": str(datetime.now(timezone.utc))}, f, indent=2)


def load_daily_spend() -> float:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if os.path.exists(DAILY_SPEND_FILE):
        try:
            with open(DAILY_SPEND_FILE, "r") as f:
                data = json.load(f)
                if data.get("date") == today:
                    return float(data.get("spent", 0))
        except Exception:
            pass
    return 0.0


def save_daily_spend(amount: float):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with open(DAILY_SPEND_FILE, "w") as f:
        json.dump({"date": today, "spent": round(amount, 4)}, f, indent=2)


def load_results() -> list:
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, "r") as f:
                return json.load(f).get("results", [])
        except Exception:
            pass
    return []


def save_results(results: list):
    with open(RESULTS_FILE, "w") as f:
        json.dump({"results": results, "updated": str(datetime.now(timezone.utc))}, f, indent=2)


# ══════════════════════════════════════════════════════════════
#  MARKET SCANNING
# ══════════════════════════════════════════════════════════════

def fetch_markets() -> list:
    try:
        resp = requests.get(
            f"{GAMMA_API}/markets",
            params={"active": "true", "closed": "false", "limit": 500},
            timeout=15
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.error(f"Failed to fetch markets: {e}")
        return []


def fetch_market_by_condition(condition_id: str) -> dict:
    try:
        resp = requests.get(
            f"{GAMMA_API}/markets",
            params={"condition_id": condition_id},
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
    except Exception as e:
        log.warning(f"Could not fetch market {condition_id[:12]}...: {e}")
    return {}


def parse_end_date(market: dict):
    end_str = market.get("endDateIso") or market.get("end_date_iso")
    if not end_str:
        return None
    try:
        return datetime.fromisoformat(end_str.replace("Z", "+00:00"))
    except Exception:
        return None


def get_best_token(market: dict):
    best = None
    for token in market.get("tokens", []):
        try:
            price = float(token.get("price", 0))
        except (ValueError, TypeError):
            continue
        if MIN_PRICE <= price <= MAX_PRICE:
            if best is None or price > best[2]:
                best = (
                    token.get("token_id") or token.get("id"),
                    token.get("outcome", "Unknown"),
                    price
                )
    return best


# ══════════════════════════════════════════════════════════════
#  MOMENTUM CHECK
# ══════════════════════════════════════════════════════════════

def check_momentum(token_id: str, current_price: float):
    """
    Pull 6h price history. If price fell >MOMENTUM_DROP_PCT% from peak, skip.
    Returns (is_safe: bool, reason: str)
    """
    try:
        end_ts   = int(datetime.now(timezone.utc).timestamp())
        start_ts = end_ts - (6 * 3600)

        resp = requests.get(
            f"{CLOB_HOST}/prices-history",
            params={"market": token_id, "startTs": start_ts, "endTs": end_ts, "fidelity": 60},
            timeout=10
        )

        if resp.status_code != 200:
            log.warning(f"  Momentum API {resp.status_code} — allowing trade")
            return True, "momentum data unavailable"

        history = resp.json().get("history", [])
        if not history or len(history) < 3:
            return True, "not enough price history"

        prices     = [float(h["p"]) for h in history if "p" in h]
        peak_price = max(prices)
        drop_pct   = (peak_price - current_price) / peak_price * 100

        if drop_pct >= MOMENTUM_DROP_PCT:
            return False, f"dropped {drop_pct:.2f}% from peak ({peak_price:.3f} -> {current_price:.3f})"
        return True, f"stable (peak drop: {drop_pct:.2f}%)"

    except Exception as e:
        log.warning(f"  Momentum check failed ({e}) — allowing trade")
        return True, f"check failed: {e}"


# ══════════════════════════════════════════════════════════════
#  OPPORTUNITY FINDER
# ══════════════════════════════════════════════════════════════

def find_opportunities(markets: list, purchased: set) -> list:
    now    = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=MAX_HOURS_TO_CLOSE)
    opps   = []

    for market in markets:
        condition_id = market.get("conditionId") or market.get("condition_id", "")
        if condition_id in purchased:
            continue

        end_date = parse_end_date(market)
        if end_date is None or end_date > cutoff or end_date < now:
            continue

        try:
            volume = float(market.get("volume", 0) or market.get("volumeNum", 0) or 0)
        except (ValueError, TypeError):
            volume = 0
        if volume < MIN_VOLUME_USDC:
            continue

        token_data = get_best_token(market)
        if token_data is None:
            continue

        token_id, outcome, price = token_data
        hours_left   = (end_date - now).total_seconds() / 3600
        expected_roi = round((1.0 - price) / price * 100, 2)

        # Momentum gate
        is_safe, momentum_reason = check_momentum(token_id, price)
        if not is_safe:
            log.info(f"  SKIPPED (momentum): {market.get('question', '')[:65]}")
            log.info(f"  Reason: {momentum_reason}")
            continue

        opps.append({
            "condition_id":    condition_id,
            "question":        market.get("question", "Unknown"),
            "outcome":         outcome,
            "token_id":        token_id,
            "price":           price,
            "volume":          volume,
            "hours_left":      round(hours_left, 1),
            "expected_roi":    expected_roi,
            "momentum_reason": momentum_reason,
            "end_date":        str(end_date),
        })

    # Combined score: 60% ROI + 40% volume
    if opps:
        max_vol = max(o["volume"] for o in opps) or 1
        for o in opps:
            o["score"] = round(0.6 * (o["expected_roi"] / 10) + 0.4 * (o["volume"] / max_vol), 4)
        opps.sort(key=lambda x: x["score"], reverse=True)

    return opps


# ══════════════════════════════════════════════════════════════
#  ORDER PLACEMENT
# ══════════════════════════════════════════════════════════════

def init_client():
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.constants import POLYGON
        from py_clob_client.clob_types import ApiCreds
        creds = ApiCreds(api_key=API_KEY, api_secret=API_SECRET, api_passphrase=API_PASSPHRASE)
        return ClobClient(host=CLOB_HOST, chain_id=POLYGON, private_key=PRIVATE_KEY, creds=creds)
    except ImportError:
        log.error("py-clob-client not installed")
        return None
    except Exception as e:
        log.error(f"Client init failed: {e}")
        return None


def check_balance(client) -> float:
    try:
        return float(client.get_balance_allowance().get("balance", 0)) / 1_000_000
    except Exception:
        return 0.0


def place_order(client, token_id: str, size_usdc: float) -> bool:
    try:
        from py_clob_client.clob_types import MarketOrderArgs
        signed = client.create_market_order(MarketOrderArgs(token_id=token_id, amount=size_usdc))
        log.info(f"  Order response: {client.post_order(signed)}")
        return True
    except Exception as e:
        log.error(f"  Order failed: {e}")
        return False


# ══════════════════════════════════════════════════════════════
#  RESOLUTION TRACKER
# ══════════════════════════════════════════════════════════════

def check_resolutions():
    log.info("=" * 60)
    log.info("  RESOLUTION CHECK — P&L REPORT")
    log.info(f"  Time (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

    positions      = load_positions()
    results        = load_results()
    resolved_ids   = {r["condition_id"] for r in results}
    newly_resolved = []

    for pos in positions:
        condition_id = pos.get("condition_id")
        if not condition_id or condition_id in resolved_ids:
            continue

        question  = pos.get("question", "Unknown")
        bought_at = pos.get("price", 0)
        outcome   = pos.get("outcome", "")
        spent     = pos.get("spent_usdc", TRADE_SIZE_USDC)

        market    = fetch_market_by_condition(condition_id)
        if not market:
            log.warning(f"  Could not fetch {condition_id[:12]}... — skipping")
            continue

        is_closed = market.get("closed", False) or market.get("resolved", False)

        if not is_closed:
            # Track unrealised P&L on open positions
            current_price = bought_at
            for token in market.get("tokens", []):
                if token.get("outcome", "").strip().lower() == outcome.strip().lower():
                    try:
                        current_price = float(token.get("price", bought_at))
                    except Exception:
                        pass
                    break
            pos["current_price"]  = current_price
            pos["unrealised_pnl"] = round((current_price - bought_at) / bought_at * spent, 4)
            pos["status"]         = "open"
            continue

        # Determine winner
        winning_outcome = None
        for token in market.get("tokens", []):
            if float(token.get("price", 0)) >= 0.99:
                winning_outcome = token.get("outcome")
                break
        if winning_outcome is None:
            winning_outcome = market.get("resolutionOutcome") or market.get("resolution_outcome")

        if winning_outcome is None:
            log.warning(f"  Cannot determine winner for: {question[:55]}")
            continue

        won        = outcome.strip().lower() == winning_outcome.strip().lower()
        shares     = round(spent / bought_at, 6)
        net_pnl    = round(shares - spent, 4) if won else round(-spent, 4)
        pct_return = round(net_pnl / spent * 100, 2)

        result = {
            "condition_id":    condition_id,
            "question":        question,
            "outcome":         outcome,
            "winning_outcome": winning_outcome,
            "bought_at":       bought_at,
            "spent_usdc":      spent,
            "payout":          round(shares, 4) if won else 0.0,
            "net_pnl":         net_pnl,
            "pct_return":      pct_return,
            "won":             won,
            "bought_on":       pos.get("bought_on", "?"),
            "resolved_on":     datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "dry_run":         pos.get("dry_run", True),
        }

        results.append(result)
        newly_resolved.append(result)
        resolved_ids.add(condition_id)
        pos["status"] = "resolved"
        time.sleep(0.5)

    save_results(results)
    save_positions(positions)

    # ── PRINT REPORT ─────────────────────────────────────────
    log.info("")
    log.info("  📊 P&L REPORT")
    log.info("  " + "─" * 56)

    if newly_resolved:
        log.info(f"  New resolutions this run: {len(newly_resolved)}")
        for r in newly_resolved:
            icon = "WIN " if r["won"] else "LOSS"
            tag  = "[DRY]" if r.get("dry_run") else "[LIVE]"
            log.info(
                f"  {tag} {icon} | ${r['spent_usdc']:.2f} -> ${r['payout']:.2f} "
                f"| {'+' if r['net_pnl'] >= 0 else ''}{r['net_pnl']:.2f} ({r['pct_return']:+.1f}%) "
                f"| {r['question'][:45]}"
            )
    else:
        log.info("  No new resolutions this run.")

    log.info("")
    all_results = load_results()

    if all_results:
        total_invested = sum(r["spent_usdc"] for r in all_results)
        total_returned = sum(r["payout"] for r in all_results)
        total_pnl      = sum(r["net_pnl"] for r in all_results)
        wins           = sum(1 for r in all_results if r["won"])
        losses         = len(all_results) - wins
        win_rate       = wins / len(all_results) * 100

        log.info("  ALL-TIME STATS")
        log.info("  " + "─" * 56)
        log.info(f"  Resolved trades : {len(all_results)}  ({wins}W / {losses}L)")
        log.info(f"  Win rate        : {win_rate:.1f}%")
        log.info(f"  Total invested  : ${total_invested:.2f}")
        log.info(f"  Total returned  : ${total_returned:.2f}")
        log.info(f"  Net P&L         : {'+' if total_pnl >= 0 else ''}{total_pnl:.2f} USDC")

        # Open positions summary
        open_pos = [p for p in positions if p.get("status") == "open"]
        if open_pos:
            unrealised = sum(p.get("unrealised_pnl", 0) for p in open_pos)
            log.info(f"  Open positions  : {len(open_pos)} (unrealised {'+' if unrealised >= 0 else ''}{unrealised:.2f})")

        log.info("")
        log.info("  FULL TRADE HISTORY")
        log.info("  " + "─" * 56)
        for r in sorted(all_results, key=lambda x: x.get("resolved_on", ""), reverse=True):
            icon = "✅" if r["won"] else "❌"
            tag  = "[DRY]" if r.get("dry_run") else "[LIVE]"
            log.info(
                f"  {icon} {tag} {r.get('resolved_on','?')} "
                f"| {'+' if r['net_pnl'] >= 0 else ''}{r['net_pnl']:.2f} ({r['pct_return']:+.1f}%) "
                f"| {r['question'][:50]}"
            )

        if open_pos:
            log.info("")
            log.info("  OPEN POSITIONS")
            log.info("  " + "─" * 56)
            for p in open_pos:
                log.info(
                    f"  {p.get('question','?')[:55]} "
                    f"| bought @ {p.get('price',0):.3f} "
                    f"| now @ {p.get('current_price', p.get('price',0)):.3f} "
                    f"| closes {p.get('end_date','?')[:10]}"
                )
    else:
        log.info("  No resolved trades yet — check back after markets close.")

    log.info("")
    log.info("  Resolution check complete.")


# ══════════════════════════════════════════════════════════════
#  MAIN SCAN
# ══════════════════════════════════════════════════════════════

def main():
    log.info("=" * 60)
    log.info("  POLYMARKET BOT — SCAN STARTING")
    log.info(f"  Time (UTC):   {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"  Mode:         {'DRYN RUN (no real orders)' if DRY_RUN else 'LIVE TRADING'}")
    log.info(f"  Trade size:   ${TRADE_SIZE_USDC} USDC")
    log.info(f"  Price range:  {MIN_PRICE} - {MAX_PRICE}")
    log.info(f"  Window:       <= {MAX_HOURS_TO_CLOSE}h to close")
    log.info(f"  Daily cap:    ${DAILY_SPEND_CAP}")
    log.info(f"  Momentum:     skip if drop > {MOMENTUM_DROP_PCT}%")
    log.info("=" * 60)

    if not DRY_RUN:
        missing = [k for k, v in {
            "PRIVATE_KEY": PRIVATE_KEY, "CLOB_API_KEY": API_KEY,
            "CLOB_SECRET": API_SECRET, "CLOB_PASSPHRASE": API_PASSPHRASE,
        }.items() if not v]
        if missing:
            log.error(f"Missing secrets: {', '.join(missing)}")
            sys.exit(1)
        client  = init_client()
        if client is None:
            sys.exit(1)
        balance = check_balance(client)
        log.info(f"  Wallet balance: ${balance:.2f} USDC")
        if balance < TRADE_SIZE_USDC:
            log.warning(f"  Low balance! ${balance:.2f} < ${TRADE_SIZE_USDC}")
    else:
        client = None

    purchased   = load_purchased()
    positions   = load_positions()
    daily_spent = load_daily_spend()
    remaining   = max(0.0, DAILY_SPEND_CAP - daily_spent)

    log.info(f"  Tracked positions : {len(purchased)}")
    log.info(f"  Daily spend       : ${daily_spent:.2f}/${DAILY_SPEND_CAP} (${remaining:.2f} left)\n")

    if remaining < TRADE_SIZE_USDC:
        log.info(f"  Daily cap reached. No trades until midnight UTC.")
        return

    log.info("  Fetching markets...")
    markets = fetch_markets()
    log.info(f"  Found {len(markets)} active markets")

    opps = find_opportunities(markets, purchased)
    log.info(f"  Passing all filters: {len(opps)}\n")

    if not opps:
        log.info("  Nothing to buy this scan.")
    else:
        for opp in opps:
            daily_spent = load_daily_spend()
            remaining   = max(0.0, DAILY_SPEND_CAP - daily_spent)
            if remaining < TRADE_SIZE_USDC:
                log.info(f"  Daily cap hit (${daily_spent:.2f}/${DAILY_SPEND_CAP}). Stopping.")
                break

            log.info(f"  OPPORTUNITY (score: {opp.get('score', 'N/A')})")
            log.info(f"     {opp['question'][:75]}")
            log.info(f"     Outcome   : {opp['outcome']}")
            log.info(f"     Price     : {opp['price']:.3f} ({opp['price']*100:.1f}c)")
            log.info(f"     ROI       : +{opp['expected_roi']:.2f}% if wins")
            log.info(f"     Volume    : ${opp['volume']:,.0f}")
            log.info(f"     Closes in : {opp['hours_left']}h")
            log.info(f"     Momentum  : OK — {opp['momentum_reason']}")

            trade_ok = DRY_RUN
            if not DRY_RUN:
                log.info("  Placing order...")
                trade_ok = place_order(client, opp["token_id"], TRADE_SIZE_USDC)

            if trade_ok:
                tag = "[DRY RUN]" if DRY_RUN else "[LIVE]"
                log.info(f"  {tag} Bought ${TRADE_SIZE_USDC} | Daily: ${daily_spent + TRADE_SIZE_USDC:.2f}/${DAILY_SPEND_CAP}")

                # Save full position detail for resolution tracking
                positions.append({
                    "condition_id": opp["condition_id"],
                    "question":     opp["question"],
                    "outcome":      opp["outcome"],
                    "token_id":     opp["token_id"],
                    "price":        opp["price"],
                    "spent_usdc":   TRADE_SIZE_USDC,
                    "expected_roi": opp["expected_roi"],
                    "end_date":     opp["end_date"],
                    "bought_on":    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                    "dry_run":      DRY_RUN,
                    "status":       "open",
                })

                purchased.add(opp["condition_id"])
                daily_spent += TRADE_SIZE_USDC

                save_purchased(purchased)
                save_positions(positions)
                save_daily_spend(daily_spent)
            else:
                log.error("  Order failed — not marking as purchased")

            time.sleep(1)

    save_purchased(purchased)
    log.info("\n  Scan complete.")


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "resolve":
        check_resolutions()
    else:
        main()
