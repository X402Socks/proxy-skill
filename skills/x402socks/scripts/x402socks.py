#!/usr/bin/env python3
"""x402socks helper: wallet, funding check, catalog, buy, status, rotate, recover, proxy check.

Secrets never leave this process:
  key   -> ~/.x402socks/key   (0600, never printed)
  token -> ~/.x402socks/token (0600, never printed)

Requires: python3 -m pip install "eth-account>=0.11" (in a local venv).
"""
import argparse, base64, json, os, secrets, subprocess, sys, tempfile, time
import urllib.error, urllib.request
from pathlib import Path

WEB = "https://x402socks.com"
PAY = "https://payments.x402socks.com"
API = "https://api.x402socks.com"
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
RPC = os.environ.get("X402SOCKS_RPC", "https://mainnet.base.org")
HOME = Path(os.environ.get("X402SOCKS_HOME", Path.home() / ".x402socks"))
KEY, TOKEN, META, RECEIPTS = HOME / "key", HOME / "token", HOME / "token.json", HOME / "receipts"


def die(msg):
    sys.exit("error: " + msg)


def secret_write(path, text):
    HOME.mkdir(parents=True, exist_ok=True)
    os.umask(0o077)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)


def read_key():
    if not KEY.exists():
        die(f"no wallet at {KEY}; run: {sys.argv[0]} wallet create")
    if KEY.stat().st_mode & 0o077:
        die(f"refusing: {KEY} is not mode 0600")
    return KEY.read_text().strip()


def read_token():
    if not TOKEN.exists():
        die(f"no token at {TOKEN}; buy a package first")
    if TOKEN.stat().st_mode & 0o077:
        die(f"refusing: {TOKEN} is not mode 0600")
    return TOKEN.read_text().strip()


def http(url, method="GET", body=None, headers=None, timeout=40):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"content-type": "application/json", "user-agent": "x402socks-skill/1", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read().decode()


def b64json(header_value):
    return json.loads(base64.b64decode(header_value).decode())


def to0x(sig):
    sig = getattr(sig, "hex", lambda: sig)()
    return sig if sig.startswith("0x") else "0x" + sig


# ---------------------------------------------------------------- wallet

def cmd_wallet(args):
    from eth_account import Account
    if args.action == "create":
        if KEY.exists():
            die(f"{KEY} already exists; refusing to overwrite")
        acct = Account.create()
        secret_write(KEY, acct.key.hex())
        print(acct.address)
        print(f"key: {KEY} (0600). Back it up offline; it is the only copy.", file=sys.stderr)
    elif args.action == "import":
        # Never regex the first 0x…64 in a wallet note: a transaction hash has
        # the same shape. Require the "Private Key:" label and cross-check the
        # declared address when the note contains one.
        import re
        note = Path(args.file).read_text()
        m = re.search(r"(?im)^\s*(?:private key|private_key|key)\s*:\s*(0x[0-9a-fA-F]{64})\b", note)
        if not m:
            die("no labelled 'Private Key: 0x…' line found in the file")
        key = m.group(1).strip()
        addr = Account.from_key(key).address
        declared = re.search(r"(?im)^\s*address\s*:\s*(0x[0-9a-fA-F]{40})\b", note)
        if declared and declared.group(1).lower() != addr.lower():
            die("declared Address: does not match the private key; refusing to import")
        if KEY.exists() and not args.force:
            die(f"{KEY} already exists; refusing to overwrite (use --force deliberately)")
        secret_write(KEY, key)
        print(addr)
        print(f"key imported from {args.file} -> {KEY} (0600); key not printed",
              file=sys.stderr)
    else:
        print(Account.from_key(read_key()).address)


def cmd_fund(args):
    from eth_account import Account
    addr = Account.from_key(read_key()).address
    data = "0x70a08231" + "0" * 24 + addr[2:].lower()
    payload = {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
               "params": [{"to": USDC_BASE, "data": data}, "latest"]}
    try:
        _, _, text = http(RPC, "POST", payload)
        bal = int(json.loads(text)["result"], 16) / 1e6
    except Exception as e:  # noqa: BLE001
        bal, note = None, f"(balance check unavailable: {e})"
    print(f"address: {addr}")
    print(f"network: Base (eip155:8453), native USDC {USDC_BASE}")
    print(f"rpc: {RPC}")
    if bal is None:
        print(note)
    else:
        print(f"balance: {bal:.6f} USDC")
    print("send USDC on Base only; no ETH needed for x402 (EIP-3009, facilitator pays gas)")


# ---------------------------------------------------------------- catalog

def catalog():
    code, _, text = http(WEB + "/catalog.json")
    if code != 200:
        die(f"catalog.json returned {code}")
    return json.loads(text)["packages"]


def cmd_quote(args):
    print(f"{'id':<14}{'usd':>8}  {'duration':>10}  {'bytes':>12}  sessions")
    for p in catalog():
        hours = p.get("duration_hours")
        print(f"{p['id']:<14}{p['price_usd']:>8.2f}  "
              f"{('none' if hours is None else str(hours) + 'h'):>10}  "
              f"{p.get('max_bytes', '-'):>12}  {p.get('max_sessions', '-')}")


# ---------------------------------------------------------------- buy

def sign_eip3009(req, address, key):
    from eth_account import Account
    from eth_utils import to_checksum_address
    now = int(time.time())
    auth = {
        "from": to_checksum_address(address),
        "to": to_checksum_address(req["payTo"]),
        "value": int(req["amount"]),
        "validAfter": now - 60,
        "validBefore": now + min(int(req.get("maxTimeoutSeconds", 300)), 300) - 5,
        "nonce": secrets.token_bytes(32),
    }
    typed = {
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
            "chainId": int(req["network"].split(":")[1]),
            "verifyingContract": to_checksum_address(req["asset"]),
        },
        "message": auth,
    }
    sig = to0x(Account.sign_typed_data(key, full_message=typed).signature)
    return {
        "signature": sig,
        "authorization": {
            "from": auth["from"], "to": auth["to"], "value": str(auth["value"]),
            "validAfter": str(auth["validAfter"]), "validBefore": str(auth["validBefore"]),
            "nonce": "0x" + auth["nonce"].hex(),
        },
    }


def save_receipt(package, amount, payment_response):
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    meta = {"package": package, "amount_atomic": amount, "bought_at": int(time.time()),
            "payment_response": payment_response}
    path = RECEIPTS / f"{int(time.time())}-{package}.json"
    secret_write(path, json.dumps(meta, indent=2))
    if payment_response:
        try:
            decoded = b64json(payment_response)
        except Exception:  # noqa: BLE001
            decoded = {}
        for k in ("transaction", "txHash", "transactionHash", "transaction_hash"):
            if decoded.get(k):
                secret_write(HOME / "settlement.json",
                             json.dumps({"tx": decoded[k], "package": package}, indent=2))
                break
    return path


def extract_token(body):
    for k in ("token", "credential", "api_key", "access_token"):
        if isinstance(body.get(k), str) and body[k]:
            return body[k]
    acct = body.get("account")
    if isinstance(acct, dict):
        for k in ("token", "credential"):
            if isinstance(acct.get(k), str) and acct[k]:
                return acct[k]
    return None


def cmd_buy(args):
    from eth_account import Account
    key = read_key()
    address = Account.from_key(key).address
    pkgs = {p["id"]: p for p in catalog()}
    pkg = pkgs.get(args.package)
    if pkg is None:
        if not args.allow_unknown:
            die(f"unknown package {args.package}; see: {sys.argv[0]} quote "
                "(test-only rails need --allow-unknown --max-usd)")
        if args.max_usd is None:
            die("--allow-unknown requires --max-usd as an absolute spend ceiling")
        price = None
    else:
        price = float(pkg["price_usd"])

    code, hdrs, text = http(f"{PAY}/v1/access/{args.package}", "POST", {})
    if code == 200:
        die("unexpected 200 without payment; not charging")
    if code != 402 or "payment-required" not in hdrs:
        die(f"expected 402 + PAYMENT-REQUIRED, got {code}: {text[:200]}")
    challenge = b64json(hdrs["payment-required"])

    req = next((a for a in challenge.get("accepts", [])
                if a.get("scheme") == "exact" and a.get("network") == "eip155:8453"), None)
    if not req:
        die("challenge has no exact/eip155:8453 requirement")
    amount = int(req["amount"])
    if req["asset"].lower() != USDC_BASE.lower():
        die(f"unexpected asset {req['asset']}")
    if price is None:
        cap = round(args.max_usd * 1_000_000)
        if amount > cap:
            die(f"amount {amount} atomic exceeds --max-usd ceiling {cap} atomic")
    else:
        expected = round(price * 1_000_000)
        if amount != expected and not args.force:
            die(f"amount {amount} != catalog price {expected} atomic; refusing (use --force to override)")
    if not args.yes:
        die(f"would pay {amount} atomic ({amount / 1e6:.6f} USDC) for {args.package} "
            f"to {req['payTo']}; re-run with --yes")

    payload = {
        "x402Version": 2,
        "resource": challenge.get("resource"),
        "accepted": req,
        "payload": sign_eip3009(req, address, key),
    }
    if challenge.get("extensions"):
        payload["extensions"] = challenge["extensions"]
    header = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()

    code, hdrs, text = http(f"{PAY}/v1/access/{args.package}", "POST", {},
                            {"PAYMENT-SIGNATURE": header})
    pr = hdrs.get("payment-response", "")
    if code != 200:
        try:
            err = str(json.loads(text).get("error") or "")[:200]
        except Exception:  # noqa: BLE001
            err = text[:200]
        hint = " settlement may have occurred: keep the tx hash, do NOT pay twice." if code == 502 else ""
        die(f"payment retry returned {code}: {err}{hint}")

    body = json.loads(text) if text.strip() else {}
    token = extract_token(body)
    if not token:
        secret_write(HOME / "purchase-response.json", text)
        die(f"200 but no token field found; raw body saved to {HOME}/purchase-response.json")
    secret_write(TOKEN, token)
    secret_write(META, json.dumps({"package": args.package, "amount_atomic": amount,
                                   "bought_at": int(time.time())}, indent=2))
    receipt = save_receipt(args.package, amount, pr)
    # Test rails can cost a single atomic unit; two decimals would print 0.00.
    paid = (f"{amount} atomic ({amount / 1e6:.6f} USDC)" if amount < 10_000
            else f"{amount / 1e6:.2f} USDC")
    print(f"bought {args.package} for {paid}")
    print(f"token saved to {TOKEN} (0600, {len(token)} chars) — value not printed")
    print(f"receipt: {receipt}")
    print("verify now:  " + sys.argv[0] + " status && " + sys.argv[0] + " check")


# ---------------------------------------------------------------- account

def summarize(body):
    keep = {}
    for k, v in body.items():
        if k in ("token", "credential", "api_key", "access_token"):
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            keep[k] = v
        elif isinstance(v, dict):
            keep[k] = {kk: vv for kk, vv in v.items()
                       if not isinstance(vv, str) or len(vv) < 80}
    return keep


def cmd_status(args):
    tok = read_token()
    code, _, text = http(WEB + "/api/token/status", "POST", {"token": tok})
    body = json.loads(text) if text.strip() else {}
    if code != 200:
        die(f"status {code}: {body.get('error') or body.get('code') or text[:200]}")
    print(json.dumps(summarize(body), indent=2, sort_keys=True))


def cmd_rotate(args):
    tok = read_token()
    code, _, text = http(API + "/api/v1/token/rotate", "POST", None,
                         {"authorization": "Bearer " + tok})
    if code != 200:
        die(f"rotate {code}: {text[:200]}")
    body = json.loads(text)
    new = extract_token(body)
    if not new:
        die("rotate succeeded but no token in response")
    secret_write(TOKEN, new)
    print("token rotated; old value is now dead everywhere. All clients must use the new one.")


def cmd_recover(args):
    from eth_account import Account
    from eth_account.messages import encode_defunct
    key = read_key()
    issued = int(time.time())
    msg = f"x402socks credential recovery v1\ntx_hash: {args.tx}\nissued_at: {issued}"
    sig = to0x(Account.sign_message(encode_defunct(text=msg), private_key=key).signature)
    code, _, text = http(PAY + "/v1/access/recover", "POST",
                         {"transaction": args.tx, "signature": sig, "issued_at": issued})
    if code != 200:
        die(f"recover {code}: {text[:300]}")
    new = extract_token(json.loads(text))
    if not new:
        die("recover returned no token")
    secret_write(TOKEN, new)
    print(f"recovered and saved a new token to {TOKEN} (not printed)")


# ---------------------------------------------------------------- proxy check

CHECKS = [("socks5", "1080", "socks5h"), ("http", "3128", "http"), ("tls", "3129", "https")]


def curl_via(proxy_url, token, url="https://api.ipify.org"):
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(HOME), suffix=".curlrc") as fh:
        os.chmod(fh.name, 0o600)
        fh.write(f'proxy = "{proxy_url}"\nproxy-user = "{token}:{token}"\n'
                 'silent\nshow-error\nmax-time = 25\n')
        cfg = fh.name
    try:
        out = subprocess.run(["curl", "-K", cfg, url], capture_output=True, text=True, timeout=40)
        return out.stdout.strip() if out.returncode == 0 else f"FAIL({out.stderr.strip()[:60]})"
    finally:
        os.unlink(cfg)


def cmd_check(args):
    tok = read_token()
    hosts = args.exit or ["us-central1"]
    try:
        _, _, text = http(WEB + "/nodes.json")
        nodes = json.loads(text).get("nodes", [])
        if not args.exit:
            hosts = [max(nodes, key=lambda n: n.get("health") == "healthy")["id"]] if nodes else hosts
    except Exception:  # noqa: BLE001
        pass
    local = subprocess.run(["curl", "-sS", "--max-time", "15", "https://api.ipify.org"],
                           capture_output=True, text=True).stdout.strip()
    print(f"host ip: {local or 'unknown'}")
    for host in hosts:
        seen = {}
        for name, port, scheme in CHECKS:
            ip = curl_via(f"{scheme}://{host}.x402socks.com:{port}", tok)
            seen[name] = ip
            print(f"{host:<14}{name:<8}{ip}")
        ips = {v for v in seen.values() if v and not v.startswith("FAIL")}
        if len(ips) == 1 and local and ips != {local}:
            print(f"  ok: all dialects exit via {ips.pop()}")
        else:
            print("  WARN: dialects disagree or match the host ip")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(prog="x402socks", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("wallet", help="create, import, or show the hot wallet")
    w.add_argument("action", choices=["create", "import", "address"], nargs="?", default="address")
    w.add_argument("file", nargs="?", help="file with a 'Private Key: 0x…' line (import only)")
    w.add_argument("--force", action="store_true", help="allow overwriting an existing key")
    w.set_defaults(fn=cmd_wallet)

    sub.add_parser("fund", help="show address and USDC balance on Base").set_defaults(fn=cmd_fund)
    sub.add_parser("quote", help="list packages and prices").set_defaults(fn=cmd_quote)

    b = sub.add_parser("buy", help="buy a package over x402")
    b.add_argument("--package", required=True)
    b.add_argument("--yes", action="store_true", help="confirm the spend")
    b.add_argument("--force", action="store_true", help="ignore catalog price mismatch")
    b.add_argument("--allow-unknown", action="store_true",
                   help="test-only: allow a package id that is absent from the public catalog")
    b.add_argument("--max-usd", type=float,
                   help="absolute spend ceiling for --allow-unknown")
    b.set_defaults(fn=cmd_buy)

    sub.add_parser("status", help="token status").set_defaults(fn=cmd_status)
    sub.add_parser("rotate", help="rotate the token").set_defaults(fn=cmd_rotate)

    r = sub.add_parser("recover", help="recover a lost token from a settlement tx")
    r.add_argument("--tx", required=True)
    r.set_defaults(fn=cmd_recover)

    c = sub.add_parser("check", help="verify egress ip per dialect")
    c.add_argument("--exit", action="append", help="exit id (repeatable)")
    c.set_defaults(fn=cmd_check)

    args = ap.parse_args()
    try:
        args.fn(args)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        die(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
