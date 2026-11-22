# PRE-TRADE INTERLOCK ASSERTION RULE (DESK POLICY)

> **Status**: ACTIVE STANDING RULE — adopted 2026-11-22 per CRO Kaizen audit (closure edition)
> **Codifies**: Kaizen Pillar 4 anti-regression rule from CRO_Kaizen_Audit_Report_2026-11-22
> **Supersedes**: nothing; extends the pre-flight gates of desk/CANONICAL_MASTER_SPECIFICATION.md
> and desk/KAIZEN_VERIFICATION_PROMPT.md §2A

---

## 1. The Rule

Before **any** order submission batch on any venue, the executor MUST assert the
venue's client-side trading interlock and halt on failure:

| Venue | Assertion (must be `True` / green) | On `False` |
| --- | --- | --- |
| Blueberry MT5 (#5126976) | `mt5.terminal_info().trade_allowed == True` (physical "Algo Trading" toolbar button GREEN) | HALT batch, log event, page operator |
| Delta Exchange India (#26902927) | authenticated API reachable + wallet balance read succeeds (credential/2FA interlock) | HALT batch, log event, page operator |

A failed assertion is a **blocking precondition**, not a warning. No order —
new, modify, or cancel — may be attempted while an interlock is red.

## 2. Mandatory Event Record

Every interlock failure MUST be persisted before paging, with at minimum:

```json
{
  "ts_utc": "<ISO-8601>",
  "host": "<windows-host>",
  "venue": "mt5|delta",
  "probe": "terminal_info().trade_allowed",
  "value": false,
  "retcode_observed": 10027,
  "batch_ids": ["<order ids suppressed>"]
}
```

Write it to `desk/events/interlock_YYYYMMDD_HHMMSS.json` and reference it in the
next `desk/log.md` round entry. The 2026-11-22 incident (retcode 10027,
AutoTrading disabled by client) left **zero on-disk event record** — this rule
exists so that never recurs.

## 3. Re-Arm Procedure (after any interlock failure)

1. Operator toggles the physical interlock (MT5 GUI button red → green; Delta
   credential/session restored).
2. Executor re-runs the assertion probe — must return `True`.
3. First submission after re-arm is a **canary**: minimum desk risk tier,
   playbook-grade setup, `retcode == 10009 (TRADE_RETCODE_DONE)` confirmed by
   readback (`orders_get()` / `get_open_orders`) before normal tiering resumes.
4. The canary's ticket + retcode are logged in the round entry.

## 4. Evidence Honesty Clause

Any venue probe the executing agent cannot run itself (Windows-only package,
missing credentials, host-only process) MUST be recorded in the round log as
`UNVERIFIED-BY-AGENT` with the operator's assertion quoted verbatim and dated.
Silently skipping an unauditabie probe is a process violation. Auditor
recomputation (arithmetic, coherence, replication) is performed on the quoted
figures and the attribution is preserved in the audit trail.

## 5. Register Sync Requirement

Every order placed, modified or cancelled on a venue MUST be reflected in
`desk/state.json` (orders/positions) and the round entry in `desk/log.md`
within one desk cycle of the action. Venue state that outruns the desk
register is an open audit finding until reconciled (observed 2026-11-22:
tickets #20388131 / #20388144 / #1705543437 live on venues, absent from
register).

## 6. Authority

This rule is issued under the CRO audit authority of the Kaizen loop
(CANONICAL_MASTER_SPECIFICATION.md) and is binding on `atg-exec`, `zai-desk`
and any operator-directed manual order entry. Amendment requires a logged
Kaizen round with root-cause justification.
