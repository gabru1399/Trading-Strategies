# Security Policy — Trading-Strategies

> **Repo layout (2026-11-21 consolidation):** the CG Order-Flow Terminal now
> lives at the **repository root** (it was `CG-Terminal/` when this policy was
> written). Wherever an older doc says `CG-Terminal/scripts/...`, read
> `scripts/...`. `HFT/` and `Delta-Fibonacci-Institutional-Business/` remain
> sibling directories.

## Immediate action required (2026-11-20)

**A Delta Exchange India API key + secret pair was committed** in two files:

- `HFT/core/delta_client.py` (hardcoded fallback credentials)
- `scripts/delta_direct.py` (hardcoded module constants — was
  `CG-Terminal/scripts/delta_direct.py`)

Both were removed (env-var loading with gitignored `.env` fallback). **Removing
them from the tip of main does NOT make them safe** — the pair remains
recoverable from git history and clones/forks indefinitely.

### You must, in this order:

1. **Rotate the API keys now** on Delta Exchange India (dashboard → API keys →
   revoke the old pair, generate a new one). Treat the committed pair as
   compromised: it grants live trading access to the account.
2. Review Delta account order history / trade log for any activity you did not
   authorise during the exposure window.
3. If the repo history must stay public, consider `git filter-repo` or BFG to
   purge the secret from history **after** rotation (rotation is the real fix;
   purging alone is not, because clones exist).
4. Going forward, load credentials exclusively from the environment or a
   gitignored `.env` (see `.env.example` files). CI enforces this with a secret
   hygiene check and a gitleaks scan.

## Credential handling rules

- No credentials, tokens, account numbers with access, or private keys may be
  committed — in code, tests, docs, or example output.
- The HFT engine refuses `--live` execution when `DELTA_API_KEY` /
  `DELTA_API_SECRET` are unset (dry-run remains available on public data).
- MT5 terminal access is Windows-host-only by design; Linux/CI environments
  import the engine with a graceful `mt5 = None` degradation.

## Reporting a vulnerability

Open a GitHub security advisory on this repository, or contact the maintainer
directly. Do not open a public issue describing exploitable details.
