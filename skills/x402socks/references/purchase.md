# Buying access with x402 (and recovering it)

Prices, recipients, and amounts come from the **runtime 402 challenge**. The
catalog is for choosing; the challenge is for paying. Never hardcode either.

## 1. Quote

```sh
curl -s https://x402socks.com/catalog.json | jq '.packages[] | {id, price_usd, max_bytes, duration_hours, max_sessions}'
# or the authoritative API
curl -s https://api.x402socks.com/api/v1/packages | jq '.packages'
```

Fields that matter: `id`, `price_usd` (USD decimal), `max_bytes`, `duration_hours`
(null = no expiry), `max_sessions`.

## 2. Ask for the challenge

```sh
curl -si -X POST https://payments.x402socks.com/v1/access/time_6h \
  -H 'content-type: application/json' -d '{}'
```

Response: `HTTP/2 402` with a base64 JSON `PAYMENT-REQUIRED` header, e.g. decoded:

```json
{
  "x402Version": 2,
  "resource": {"url": "https://payments.x402socks.com/v1/access", "description": "Create an x402socks proxy access account", "mimeType": "application/json", "serviceName": "x402socks"},
  "accepts": [{
    "scheme": "exact",
    "network": "eip155:8453",
    "amount": "1000000",
    "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "payTo": "0x73BAE3c48d34d71C4CEa76DFdaa3bE2cF4d335a1",
    "maxTimeoutSeconds": 300,
    "extra": {"name": "USD Coin", "version": "2"}
  }],
  "extensions": {"bazaar": {…}}
}
```

Guardrails before signing:

- select `scheme == "exact"` and `network == "eip155:8453"` (Base);
- assert `int(amount) == round(price_usd * 1_000_000)` for the package you chose;
- assert `asset` is native USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`;
- if anything looks off, stop. A wrong recipient or amount is unrecoverable.

## 3. Sign an EIP-3009 authorization

`extra.name` / `extra.version` are the token's EIP-712 domain. Domain:
`{name, version, chainId, verifyingContract: asset}`.

```
TransferWithAuthorization(address from,address to,uint256 value,uint256 validAfter,uint256 validBefore,bytes32 nonce)
```

```python
from eth_account import Account
from eth_utils import to_checksum_address
import secrets, time

now = int(time.time())
auth = {
    "from": to_checksum_address(wallet_address),
    "to": to_checksum_address(req["payTo"]),
    "value": int(req["amount"]),
    "validAfter": now - 60,
    "validBefore": now + min(int(req["maxTimeoutSeconds"]), 300) - 5,
    "nonce": bytes.fromhex(secrets.token_bytes(32).hex()),
}
sig = Account.sign_typed_data(private_key, full_message={
    "types": {
        "EIP712Domain": [
            {"name": "name", "type": "string"}, {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"},
        ],
        "TransferWithAuthorization": [
            {"name": "from", "type": "address"}, {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"}, {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"}, {"name": "nonce", "type": "bytes32"},
        ],
    },
    "primaryType": "TransferWithAuthorization",
    "domain": {
        "name": req["extra"]["name"], "version": req["extra"]["version"],
        "chainId": 8453, "verifyingContract": to_checksum_address(req["asset"]),
    },
    "message": auth,
}).signature.hex()
```

## 4. Build `PAYMENT-SIGNATURE` and retry

Payload (x402 v2), base64-encoded into the header:

```json
{
  "x402Version": 2,
  "resource": { …copied verbatim from the challenge… },
  "accepted": { …the requirement object you signed… },
  "payload": {
    "signature": "0x…",
    "authorization": {
      "from": "0x…", "to": "0x…", "value": "1000000",
      "validAfter": "1792000000", "validBefore": "1792000300",
      "nonce": "0x…"
    }
  },
  "extensions": { …echo the challenge extensions… }
}
```

```sh
curl -sS -X POST https://payments.x402socks.com/v1/access/time_6h \
  -H 'content-type: application/json' \
  -H "PAYMENT-SIGNATURE: $B64" -d '{}'
```

`accepted` must be the requirement you signed, not a re-shaped copy. Echo
`extensions` unchanged — the spec requires the client to carry them.

## 5. On success

- `200` with a one-time credential body containing the token. Save it to
  `~/.x402socks/token` immediately, `chmod 600`. Do not print it.
- The `PAYMENT-RESPONSE` header carries settlement metadata (including the
  transaction hash). Save it: that hash is the only way to recover a lost
  token without paying again.
- Then run `x402socks.py status` and `x402socks.py check`.

If the response body has no obvious `token` field, look for a credential string
and store the whole body in a `0600` file rather than guessing.

## Errors

| Status | Meaning | Action |
|---|---|---|
| `402` | challenge / payment not accepted | read `error`; do not resend the same signature |
| `404` | package id not in catalog | re-quote |
| `502` | settled, provisioning failed | keep tx hash, retry the POST later or use recovery; never pay twice |

`settlement_pending` (broadcast but unconfirmed) is not a failure: keep the tx
hash and reconcile instead of re-signing.

## Recovery (no new payment)

```sh
python3 scripts/x402socks.py recover --tx 0xSETTLEMENT_TX_HASH
```

Signs an EIP-191 message with the paying wallet:

```
x402socks credential recovery v1
tx_hash: 0xSETTLEMENT_TX_HASH
issued_at: 1792000000
```

`issued_at` must be within ±10 minutes of now, so sign fresh each time. POST it
to `https://payments.x402socks.com/v1/access/recover` as
`{"transaction":"0x…","signature":"0x…","issued_at":1792000000}`. The response
contains the account and a new token; save it over the old one.

Never try to replay the original `PAYMENT-SIGNATURE` for recovery — the service
rejects it on purpose, because settlement calldata is public.

## Rotation

```sh
python3 scripts/x402socks.py rotate
# POST https://api.x402socks.com/api/v1/token/rotate  Authorization: Bearer <token>
```

Response: `{"account":{…},"token":"NEW_TOKEN"}`. The presented token stops
working immediately everywhere — update every client you control in the same
step. This is the correct response to suspected exposure. If the token is
already lost, use recovery, not rotation.

## Token status

```sh
python3 scripts/x402socks.py status
# POST https://x402socks.com/api/token/status  {"token": "…"}
```

Shows active/inactive, expiry, bytes used against the plan. Run it at the start
of every session; a token that is still valid needs no purchase.
