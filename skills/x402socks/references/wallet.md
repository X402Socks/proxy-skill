# Wallet: get an EVM address, fund it with USDC on Base

You need a wallet **you control the key of** — an exchange account or a
watch-only address cannot sign the x402 authorization.

## Create one

Recommended (helper in this skill):

```sh
python3 skills/x402socks/scripts/x402socks.py wallet create
# -> 0x1234...abcd        (public address; safe to share)
# key written to ~/.x402socks/key, mode 0600
```

Alternative (Foundry):

```sh
cast wallet new            # prints Address + Private key; store the key yourself
cast wallet new --json     # machine-readable
```

If the key already exists elsewhere, import it by writing the hex to
`~/.x402socks/key` with `chmod 600` — or keep using your own signer and pass the
key path via `--key` where the helper allows it.

Verify what you have:

```sh
python3 scripts/x402socks.py wallet address   # 0x… (public)
ls -l ~/.x402socks/key                        # -rw------- (must be 0600)
```

## Fund it

Send **native USDC on Base mainnet** to the address:

- network: Base (`eip155:8453`)
- token: native USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
- amount: the package price + a small buffer (e.g. $2–$5 for a $1 plan)

Ways to get it there: withdraw USDC from an exchange and choose **Base** as the
network, bridge from another chain, or transfer from an existing wallet. Some
exchanges label it "Base" and some "Base (ERC-20)" — both mean the same chain
here.

Warnings that cost real money:

- **Wrong network = lost funds.** USDC sent on Ethereum, BNB Chain, Arbitrum,
  Optimism, or Solana is not spendable by the x402 service.
- **Bridged USDC.e is not accepted.** Base has a second dollar token
  (`0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA`). Only the native contract above
  is used by the challenge.
- **No ETH needed** for the x402 rail. The EIP-3009 authorization is relayed by
  the facilitator, which pays gas. (The manual web checkout is different: there
  you send the transfer yourself and need gas on that chain.)
- Check the address character-by-character or paste it; one wrong character is
  an unrecoverable transfer.

Check the balance:

```sh
python3 scripts/x402socks.py fund
```

It prints the address, the live native-USDC balance, and whether it covers the
cheapest package. Internally it calls `balanceOf` on Base through a public RPC;
if the RPC is rate-limited, retry later or check the address in any Base
explorer.

Wait for 1–2 confirmations before buying, then run `quote` / `buy` from
`SKILL.md`.

## Key hygiene

Non-negotiables:

1. Mode `0600`, inside `~/.x402socks/` (or another protected path outside any
   Git working tree).
2. Never `cat`, print, echo, log, screenshot, or paste the key. Agents: do not
   read the file into your context — call the helper, which loads it in-process.
3. Never put the key in an environment variable that a shared process can read,
   in a URL, in shell history (`export KEY=…` is history), or in a CLI argument
   (visible in `ps`).
4. Never commit it, never include it in a Docker image, never sync it to a
   cloud folder or notes app.
5. Keep the balance small. This is a hot wallet by design: fund the next
   purchase, not a treasury.
6. Back it up once, offline, before funding. If the host dies and you have no
   backup, the remaining balance is gone.

If the key leaks:

1. Immediately move the remaining USDC to a fresh address.
2. Treat the address as burned; create a new wallet.
3. Rotate any token that was bought with it (`x402socks.py rotate`), because the
   old token may have been captured alongside it.
4. Tell the user plainly what happened; do not quietly continue.

## What is safe to share

- The public address (`0x…`) — safe, and needed to receive funds.
- A transaction hash — safe, and needed for recovery support.
- The token — **secret**. It is the credential for the proxy.
- The private key — **secret**, never leaves the host.
