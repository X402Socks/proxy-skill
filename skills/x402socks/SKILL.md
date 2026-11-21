---
name: x402socks
description: Buy and use x402socks.com proxy access — a paid SOCKS5 and HTTP CONNECT (plain and TLS) egress proxy with regional exits, payable in USDC on Base over the x402 protocol. Use when a task needs a region-selectable egress IP for web scraping, Selenium/Playwright/Chromium automation, API calls, geo testing, or when the user mentions x402socks, x402 proxy, SOCKS5 proxy for agents, or paid proxy access.
---

# x402socks — buy egress, then run the job

x402socks.com is a **proxy service**. Traffic leaves from the exit node you pick,
which is what lets you choose a region and keeps your own host IP out of the
target's logs. It is not an anonymity network: anonymity is a side effect of
forwarding, not the product.

Paid access = one **token** (not an account). Pay with **USDC on Base**, get the
token once, then use it as the SOCKS5/HTTP proxy username *and* password.

Endpoints, all three dialects on **all eight** exits (`us-west1`, `us-central1`,
`us-east1`, `us-north1`, `eu-central1`, `eu-north1`, `asia-central1`,
`asia-west1`):

| Dialect | Port | Proxy URL |
|---|---|---|
| SOCKS5 | 1080 | `socks5h://exit:1080` — default, best for automation |
| HTTP CONNECT | 3128 | `http://exit:3128` — plaintext hop |
| HTTP CONNECT over TLS | 3129 | `https://exit:3129` — encrypted hop, browsers |

Nothing is deprecated and no dialect is preferred by the service. Use `socks5h`
for scripts, `:3129` for Chrome-family tooling.

## The loop

```
wallet  ->  fund USDC (Base)  ->  quote  ->  buy  ->  verify  ->  use
```

### 0. Install the helper once

```sh
python3 -m pip install --user "eth-account>=0.11"
cd <skill-dir>            # the folder containing this SKILL.md
S=scripts/x402socks.py
```

Everything below uses `$S`, relative to the skill directory — resolve it to an
absolute path if your runtime changes the working directory. All state lives in
`~/.x402socks/` (override with `X402SOCKS_HOME`), mode `0600`.

### 1. Get an EVM address

```sh
python3 $S wallet create     # prints the public 0x address, writes the key 0600
python3 $S wallet address    # print the address again (safe)
```

Details, alternatives (`cast wallet new`), and imports: `references/wallet.md`.

### 2. Fund it with USDC on Base

Send **native USDC on Base** (`eip155:8453`, `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`)
to that address. Send the package price plus a small buffer.

```sh
python3 $S fund             # prints address + live USDC balance on Base
```

No ETH is needed: x402 uses EIP-3009, the facilitator pays gas. Do not send USDC
on Ethereum, BNB, Arbitrum, or bridged USDC.e — it will not be spendable here.

### 3. Get the packages and pick one

```sh
python3 $S quote            # table from https://x402socks.com/catalog.json
```

| id | price | what it buys |
|---|---|---|
| `time_6h` | $1.00 | 6 h, 1 GB, 1 session — cheapest single-job entry |
| `time_1d` | $3.59 | 24 h, 10 GB |
| `time_7d` | $9.99 | 7 days, 75 GB |
| `usage_5gb` | $6.99 | 5 GB, no expiry |
| `usage_50gb` | $34.99 | 50 GB, no expiry |
| `multi_agent` | $29.99 | 30 days, 300 GB, **5 sessions** |

Pick by shape of the job, not by price alone:
short scrape/test run → `time_6h`; unknown duration but bounded bytes → `usage_*`;
multi-day or repeated runs → `time_7d`; several agents/processes in parallel →
`multi_agent`. Re-quote at purchase time — the catalog is authoritative.

### 4. Buy

```sh
python3 $S buy --package time_6h            # dry run: shows exact amount + recipient
python3 $S buy --package time_6h --yes      # signs and pays
```

The dry run is the spend confirmation: it fetches the live challenge and stops
before signing. `--yes` performs the whole x402 v2 flow: `POST /v1/access/{id}`
→ `402` + `PAYMENT-REQUIRED` → EIP-3009 signature → retry with
`PAYMENT-SIGNATURE` → `200` + token. The script also refuses to sign if the
challenge amount does not match the catalog price, unless `--force` is given. The token is written to `~/.x402socks/token` (0600), settlement
metadata to `~/.x402socks/receipts/`, and the tx hash to
`~/.x402socks/settlement.json` — that hash is your recovery key, keep it.

Manual fallback and the exact payload: `references/purchase.md`.

### 5. Verify before you rely on it

```sh
python3 $S status           # active, expiry, bytes used
python3 $S check            # 3 tunnels (1 per dialect) + egress IP comparison
```

`check` must show a different IP than your host and the same IP for all three
dialects of one exit. A `200` from the payment service alone is not proof of a
working proxy.

### 6. Keep the token across sessions

- It lives in `~/.x402socks/token`, mode `0600`. Start every session with
  `python3 $S status` instead of re-buying.
- Lost token but you still have the tx hash → `python3 $S recover --tx 0x…`
  (free, no new payment).
- Suspected exposure → `python3 $S rotate` (old token dies immediately).
- Never copy the token into a repo, `.env`, chat, a URL, browser storage,
  logs, or a screenshot.

### 7. Use it

Selection, back-off, Selenium/Playwright, and scraping patterns:
`references/proxy-usage.md`. The two rules that matter most:

1. Reuse one client/session with keep-alive; do not open a tunnel per request.
2. On an auth rejection right after closing a tunnel, wait ~1 s and back off
   (1s, 2s, 4s). That is flapping protection, not a bad token.

## Hard rules — secrets

- **The private key is never read by you.** Do not `cat`, print, echo, log, or
  paste `~/.x402socks/key`. Do not pass it as a CLI argument (it lands in `ps`).
  Let the helper script load it in-process.
- **Never send the key or token to a model, chat, ticket, or third-party API.**
- Treat `~/.x402socks/` as a hot wallet: keep only the next purchase's worth of
  USDC there, and back the key up offline once (it is the only copy).
- If a key or token leaks: move funds out immediately, rotate the token, and
  assume the old value is burned. Do not "test" whether it still works.

## Failure playbook

| Symptom | Meaning | Action |
|---|---|---|
| `407` with a fresh token | token expired/inactive | `status`, then buy or recover |
| `407` immediately after a reconnect | deliberate back-off | wait 1 s, retry with backoff |
| `402` again after paying | payment did not validate | do **not** pay twice; read error, check `receipts/` |
| `502` from `/v1/access` | settled but provisioning failed | keep tx hash, retry later or `recover` |
| tunnel opens, wrong IP | exit healthy but not the one you meant | `curl https://x402socks.com/nodes.json` |
| `curl` hangs on `https://exit:3128` | `:3128` is plaintext-only | use `http://:3128` or `https://:3129` |

## Don't

- Don't buy a second plan to "fix" an auth error; check status first.
- Don't scrape through all eight exits in parallel on a 1-session plan.
- Don't hardcode prices, recipients, or amounts — read the runtime `402`
  challenge; it is authoritative.
- Don't claim the proxy proves anonymity or untraceability to the user.
