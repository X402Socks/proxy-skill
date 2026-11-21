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
python3 -m pip install --user "eth-account>=0.11"
```

## Layout

```
skills/x402socks/
  SKILL.md                     the loop: wallet -> fund -> quote -> buy -> verify -> use
  references/wallet.md         EVM address, funding with USDC on Base, key hygiene
  references/purchase.md       x402 v2 purchase, errors, recovery, rotation
  references/proxy-usage.md    exits, Selenium/Playwright, scraping, back-off
  scripts/x402socks.py         wallet / fund / quote / buy / status / rotate / recover / check
llms.txt                       mirror of https://x402socks.com/llms.txt
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

## Secrets

The private key and the proxy token live in `~/.x402socks/` at mode `0600` and
are never printed by the helper. Do not read, copy, log, or commit either one.
The wallet is a hot wallet: keep only the next purchase's USDC in it.
