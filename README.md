# x402socks skill

Agent skill for buying and using [x402socks.com](https://x402socks.com) proxy
access: SOCKS5, HTTP CONNECT, and HTTP CONNECT over TLS on eight regional
exits, paid in USDC on Base over the x402 protocol.

## Install

```sh
npx skills add X402Socks/skill

# or clone and copy
git clone https://github.com/X402Socks/skill
cp -r skills/x402socks ~/.claude/skills/     # Claude Code
cp -r skills/x402socks ~/.agents/skills/     # OpenCode / generic agents
```

Requires Python 3.9+ and `eth-account`:

```sh
python3 -m venv .venv
PIP_NO_CACHE_DIR=1 .venv/bin/pip -q install "eth-account>=0.11"
```

Keep dependencies and all runtime state inside the working directory.

## Layout

```
skills/x402socks/
  SKILL.md                     the loop: wallet -> fund -> quote -> buy -> verify -> use
  references/wallet.md         EVM address, funding with USDC on Base, key hygiene
  references/purchase.md       x402 v2 purchase, errors, recovery, rotation
  references/proxy-usage.md    exits, Selenium/Playwright, scraping, back-off
  scripts/x402socks.py         wallet / fund / quote / buy / status / rotate / recover / check
llms.txt                       mirror of https://x402socks.com/llms.txt
FIRE_DRILL.md                  cold-start acceptance test (buy, 5 exits, 1 GB cap, report)
ACTION_PLAN.md                 pending work on the web docs (proxy-web lane)
```

## Quick start

```sh
cd skills/x402socks
python3 scripts/x402socks.py wallet create     # prints the public address
# send native USDC on Base to that address
python3 scripts/x402socks.py fund
python3 scripts/x402socks.py quote
python3 scripts/x402socks.py buy --package time_6h --yes
python3 scripts/x402socks.py status
python3 scripts/x402socks.py check
```

Then use the token as the proxy username **and** password:

```sh
curl --proxy socks5h://us-central1.x402socks.com:1080 \
     --proxy-user "$TOKEN:$TOKEN" https://api.ipify.org
```

## Acceptance run — sample output

The skill was exercised end-to-end against the live service on 2026-11-21 with
an operator-funded wallet. Secret values are elided below; only public addresses,
hashes, and metadata are shown. The validation used a **test rail priced at one
atomic unit** (`0.000001 USDC`); the same commands work for any catalog package
with a real price and a funded wallet.

```console
$ .venv/bin/python skills/x402socks/scripts/x402socks.py wallet address
0x8614b54ea95Cf9b8C2D507968842821F632B566c

$ .venv/bin/python skills/x402socks/scripts/x402socks.py fund
address: 0x8614b54ea95Cf9b8C2D507968842821F632B566c
network: Base (eip155:8453), native USDC 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
rpc: https://base-rpc.publicnode.com
balance: 0.766400 USDC
send USDC on Base only; no ETH needed for x402 (EIP-3009, facilitator pays gas)

$ .venv/bin/python skills/x402socks/scripts/x402socks.py quote
id                 usd    duration         bytes  sessions
multi_agent      29.99        720h  322122547200  5
time_1d           3.59         24h   10737418240  1
time_6h           1.00          6h    1073741824  1
time_7d           9.99        168h   80530636800  1
usage_50gb       34.99         none   53687091200  1
usage_5gb         6.99         none    5368709120  1

$ .venv/bin/python skills/x402socks/scripts/x402socks.py buy --package <id>
error: would pay <amount> atomic (<usd> USDC) for <id> to 0x73BA…35a1; re-run with --yes

$ .venv/bin/python skills/x402socks/scripts/x402socks.py buy --package <id> --yes
bought <id> for 1 atomic (0.000001 USDC)
token saved to …/.x402socks/token (0600, 43 chars) — value not printed
receipt: …/.x402socks/receipts/1795255313-<id>.json
verify now:  …/x402socks.py status && …/x402socks.py check

$ .venv/bin/python skills/x402socks/scripts/x402socks.py status
{
  "account_id": "ab9a2afa1edb776711be2e17ddd69bef",
  "connections": {"active": 0, "nodes": [], "recent": 0},
  "expires_at": "2026-11-21T11:01:53.755160926Z",
  "status": "active",
  "usage": {"bytes_received": 0, "bytes_sent": 0, "seconds": 0}
}

$ .venv/bin/python skills/x402socks/scripts/x402socks.py check --exit us-west1
host ip: 113.173.44.88
us-west1      socks5  94.183.185.170
us-west1      http    94.183.185.170
us-west1      tls     94.183.185.170
  ok: all dialects exit via 94.183.185.170
```

Observed exit geolocation (eight exits probed, all non-host IPs):

```text
us-west1       94.183.185.170   Fremont, California  US
us-central1    216.75.142.108   Dallas, Texas        US
us-east1       107.175.243.169  Dallas, Texas        US
us-north1      107.149.151.183  San Jose, California US
eu-central1    95.182.87.151    Paris                FR
eu-north1      46.8.230.51      Riga                 LV
asia-central1  160.191.77.231   Singapore            SG
asia-west1     168.144.126.207  Bengaluru            IN
```

## Overflow test outline (for others)

This is the shape of the acceptance run. Use a **real catalog package** and its
real price — e.g. `time_6h` at **$1.00**, with at least that much USDC on Base —
not a hidden test rail. Keep every file inside the working directory and never
print the key or token.

1. **Prepare:** local venv, `PIP_NO_CACHE_DIR=1 .venv/bin/pip install
   "eth-account>=0.11"`, gitignore `.x402socks/` and `artifacts/`, set
   `X402SOCKS_HOME` and `X402SOCKS_RPC=https://base-rpc.publicnode.com`.
2. **Wallet:** `wallet create` (or `wallet import ./WALLET.md` for a labelled
   note), report only the public address, wait for funding, then `fund`.
3. **Read the contract:** fetch `https://x402socks.com/llms.txt` and
   `https://x402socks.com/.well-known/x402`; run `quote` and pick a package.
4. **Buy:** dry-run `buy --package <real-id>`, decode the 402 challenge to
   confirm network/asset/amount, then `buy --package <real-id> --yes`. Save the
   settlement hash; never pay twice.
5. **Verify:** `status`, then `check --exit <exit>` — all three dialects must
   agree on one non-host IP.
6. **Baseline:** `curl https://ipinfo.io/ip` plus its `/json` geolocation record;
   optionally time a direct 100 MB download.
7. **Exits:** open tunnels to at least five exits spanning US/EU/Asia, record
   each IP and geolocation, and prove `:3128` and `:3129` on one additional exit.
8. **Throughput:** download the 100 MB test files from the EU, US, and Asia OVH
   speedtest hosts, recording TTFB, connect time, total time, bytes, and speed.
   Long streams can be cut by an exit; record partial transfers or use HTTP
   Range chunks so each session stays short.
9. **Quota:** repeat downloads until the service refuses a new tunnel, calling
   `status` between rounds. Disconnection at the plan's byte allowance is the
   expected success condition — a `407`/SOCKS rejection is not a failure.
10. **Report:** summarize timings, payment evidence, token and exit behavior,
    status fields, baseline vs proxied results, and any failures. Scan the
    report for key/token strings before sharing it.

In the validation run the purchase and exit phases passed, but the test rail's
accounts were deactivated well below its advertised 1 GB allowance and long
streams were cut at ~30–60 s. That is a service finding, not the expected quota
behavior; it is documented in the run report, not used as a reason to re-buy.

## Secrets

The private key and the proxy token live in `~/.x402socks/` at mode `0600` and
are never printed by the helper. Do not read, copy, log, or commit either one.
The wallet is a hot wallet: keep only the next purchase's USDC in it.
