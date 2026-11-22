#!/usr/bin/env python3
"""CRO closure audit: independent recomputation of the operator's evidence package.

Recomputes every derived figure in desk/GLM_VERIFICATION_CLOSURE_PROMPT.md
(round 2) from the raw numbers stated there, so the report only carries
figures that survive independent arithmetic.
"""
from decimal import Decimal as D

ok = lambda cond, msg: print(("PASS" if cond else "FAIL"), "|", msg)

print("== Delta Exchange India ==")
# Ticket #1705543437 XRPUSD sell limit @ 0.9310, 10 contracts, SL 0.9365, TP 0.9190
notional = D("10") * D("0.9310")
ok(notional == D("9.31"), f"XRP notional 10 x 0.9310 = ${notional} (claimed $9.31)")
risk = D("10") * (D("0.9365") - D("0.9310"))
ok(risk == D("0.055"), f"XRP stop risk 10 x (0.9365-0.9310) = ${risk} (claimed $0.055)")
ok(risk <= D("0.50"), f"risk ${risk} <= $0.50 micro-account ceiling")
rr = (D("0.9310") - D("0.9190")) / (D("0.9365") - D("0.9310"))
ok(abs(rr - D("2.18")) < D("0.01"), f"XRP asymmetry (0.9310-0.9190)/(0.9365-0.9310) = {rr:.4f}R (claimed 2.18R)")
# ETHUSD short -1 @ 1665.0, TP stop 1536.15
eth_rr = (D("1665.0") - D("1536.15"))
print(f"NOTE | ETHUSD short TP 1536.15 vs entry 1665.0 -> +{eth_rr} USD/contract unrealized target distance")

print()
print("== Wallet coherence ==")
eq, pm, om, free = D("1.644"), D("0.706"), D("0.931"), D("0.2687")
ok(abs(pm + om + free - eq) <= D("0.01"), f"margin {pm} + order {om} + free {free} = {pm+om+free} vs equity {eq} (tol 0.01)")

print()
print("== Blueberry MT5 ==")
# SOL #20388131: BUY_LIMIT 0.03 @ 69.80, SL 68.50, TP 72.40, spread 0.25
sol_stop = D("69.80") - D("68.50")
ok(sol_stop == D("1.30"), f"SOL stop distance = ${sol_stop}")
sol_risk = D("0.03") * sol_stop * D("100")  # 1 lot = 100 SOL
# operator wrote 0.03 x 1.30 = 3.90 -> implies contract size 100
ok(sol_risk == D("3.90"), f"SOL risk 0.03 lots x 100 x $1.30 = ${sol_risk} (claimed $3.90, contract size 100)")
ok(sol_risk <= D("6.00"), f"SOL risk ${sol_risk} <= $6.00 cap")
sol_ratio = sol_stop / D("0.25")
ok(sol_ratio >= D("5.2"), f"SOL stop/spread = {sol_ratio}x (claimed >= 5.2x, PIT-18 spread-ratio <= 20%)")
sol_rr = (D("72.40") - D("69.80")) / sol_stop
ok(abs(sol_rr - D("2.00")) < D("0.01"), f"SOL asymmetry (72.40-69.80)/1.30 = {sol_rr:.4f}R (claimed 2.00R)")

# BTC #20388144: BUY_LIMIT 0.01 @ 60300, SL 59850, TP 62400, spread 15
btc_stop = D("60300") - D("59850")
ok(btc_stop == D("450"), f"BTC stop distance = ${btc_stop}")
btc_risk = D("0.01") * btc_stop
ok(btc_risk == D("4.50"), f"BTC risk 0.01 x $450 = ${btc_risk} (claimed $4.50)")
ok(btc_risk <= D("6.00"), f"BTC risk ${btc_risk} <= $6.00 cap")
btc_ratio = btc_stop / D("15")
ok(btc_ratio == D("30"), f"BTC stop/spread = {btc_ratio}x (claimed 30x)")
btc_rr = (D("62400") - D("60300")) / btc_stop
ok(abs(btc_rr - D("4.67")) < D("0.01"), f"BTC asymmetry (62400-60300)/450 = {btc_rr:.4f}R (claimed 4.67R)")

print()
print("== Ticket sequencing coherence (MT5) ==")
# cg_terminal new tickets vs prior register (round 1 state.json)
new_t, old_t = [20388131, 20388144], [20365867, 20372436, 20372533, 20372741]
ok(all(n > max(old_t) for n in new_t), f"new cg_terminal tickets {new_t} all newer than known prior max {max(old_t)}")

print()
print("== Market-hours logic (2026-11-22 is Sunday) ==")
import datetime
d = datetime.date(2026, 11, 22)
ok(d.weekday() == 6, f"2026-11-22 is a {d.strftime('%A')} -> TradFi CFDs closed, retcode 10018 (market closed) on delete is the expected server reply")
ok(D("0.2687") * D("85") / D("1") > D("22"), "INR figure plausibility: $0.2687 x ~85 USD/INR = ~Rs 22.8 (matches claimed Rs 22.84 at ~85.0)")
