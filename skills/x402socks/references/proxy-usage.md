# Using the proxy: Selenium, Playwright, scrapers

Token = proxy username **and** password. Same token on all exits and all three
dialects. Choose the dialect by what your client can authenticate with, not by
which one sounds faster.

## Pick an exit

```sh
curl -s https://x402socks.com/nodes.json | jq -r '.nodes[] | [.id, .label, .health, .disabled] | @tsv'
```

- Choose the exit geographically closest to the **target**, not to your host —
  what matters is that the target sees a plausible region and that the last hop
  is short.
- One exit per target for the whole job: switching mid-session changes the
  source IP and usually looks like a hijacked session.
- Skip `disabled: true` and non-`healthy` nodes. Do not retry a down exit
  through another dialect; it is the same node.

## curl and plain HTTP clients

```sh
# SOCKS5, remote DNS (recommended)
curl --proxy socks5h://us-central1.x402socks.com:1080 \
     --proxy-user "$TOKEN:$TOKEN" https://api.ipify.org

# HTTP CONNECT over TLS
curl --proxy https://eu-north1.x402socks.com:3129 \
     --proxy-user "$TOKEN:$TOKEN" https://api.ipify.org

# HTTP CONNECT, plaintext
curl --proxy http://us-east1.x402socks.com:3128 \
     --proxy-user "$TOKEN:$TOKEN" https://api.ipify.org
```

`--proxy-user` puts the token in the process table. On a shared host, read it
from a `0600` curl config (`-K`) or use the Python helper instead.

Python (`pip install "requests[socks]"` / `"httpx[socks]"`):

```python
import os, requests
t = open(os.path.expanduser("~/.x402socks/token")).read().strip()
p = f"socks5h://{t}:{t}@us-central1.x402socks.com:1080"
s = requests.Session(); s.proxies = {"http": p, "https": p}
print(s.get("https://api.ipify.org", timeout=30).text)
```

```python
import httpx
t = open(os.path.expanduser("~/.x402socks/token")).read().strip()
with httpx.Client(proxy=f"socks5h://{t}:{t}@us-central1.x402socks.com:1080", timeout=30) as c:
    print(c.get("https://api.ipify.org").text)
```

`requests` needs `socks5h` for DNS-at-exit — `socks5` resolves locally, which can
leak the query and break split-horizon DNS. `httpx` takes `socks5://`; if remote
resolution matters, confirm it against your version instead of assuming.

## Browsers: Chrome-family tools cannot send SOCKS5 credentials

Chromium delegates SOCKS5 auth to the OS, which has no prompt, so a token cannot
be typed into `--proxy-server=socks5://…`. Two workable options:

**A. Local bridge (works for Selenium, Playwright, Puppeteer, headless).**
Run an unauthenticated proxy on loopback that injects the credentials upstream:

```sh
# gost v3
go install github.com/go-gost/gost/v3/cmd/gost@latest   # or: brew install gost
gost -L http://127.0.0.1:8118 \
     -F socks5://TOKEN:TOKEN@us-central1.x402socks.com:1080
# TLS upstream instead: -F https://TOKEN:TOKEN@us-central1.x402socks.com:3129
```

Then point the browser at `http://127.0.0.1:8118`. Keep the bridge bound to
`127.0.0.1` only — it holds your token in its command line, so run it on a host
you control and stop it when the job ends.

Selenium:

```python
from selenium import webdriver
o = webdriver.ChromeOptions()
o.add_argument("--proxy-server=http://127.0.0.1:8118")
o.add_argument("--headless=new")
d = webdriver.Chrome(options=o)
d.get("https://api.ipify.org")     # must equal the exit IP, not your host IP
```

Playwright:

```python
b = p.chromium.launch(proxy={"server": "http://127.0.0.1:8118"})
```

Playwright can also authenticate an HTTP(S) proxy directly
(`proxy={"server": "https://us-central1.x402socks.com:3129", "username": TOKEN, "password": TOKEN}`)
but not SOCKS5, because Chromium will not send SOCKS5 credentials. For SOCKS5,
use the bridge.

**B. Plaintext HTTP CONNECT without a bridge.** `--proxy-server=http://exit:3128`
plus manual credential entry works interactively, but headless runs have nobody
to answer the `407` dialog. Not suitable for automation.

After the first page load, assert the egress IP and stop early if it matches
your host — a silent fallback to direct traffic is the most common failure in
browser automation.

## Scraping patterns that survive

- **One client, many requests.** Reuse the `Session`, keep connections alive.
  Opening a tunnel per request triggers rapid-reconnect back-off and inflates
  session use.
- **Back-off on auth rejection after a reconnect.** Close→reconnect inside ~1 s
  gets `407`/SOCKS auth failure by design. Wait 1 s, then 2 s, 4 s, capped.
  Do not rotate the token or buy again.
- **Retry 5xx and timeouts, not 407.** A 407 means credentials/plan, or the
  back-off above. Retrying harder cannot fix either.
- **Moderate concurrency.** The default plans are 1 session; `multi_agent` is 5.
  Start with 4–8 parallel requests inside one session and watch
  `x402socks.py status` for byte growth and errors before scaling.
- **Timeouts are your friend.** 20–30 s connect/read; a stuck exit is better
  replaced by a healthy one than waited on.
- **Don't mix identities.** If the target sets cookies/CSRF tied to an IP, keep
  one exit for that domain for the whole run.
- **Estimate bytes before a big job.** `status` reports `bytes_used`; a 1 GB
  plan is consumed by both directions, including asset downloads — do a 10-page
  sample, measure, then size the plan.

## Verify, then report

```sh
python3 scripts/x402socks.py check
```

Prints token state plus the egress IP for one exit on each dialect. A healthy
result is: token active, all three dialects return the **same** exit IP, and it
differs from your host's IP. Do this before a long run and once at the end.

Do not describe the proxy to the user as anonymity or as making them
untraceable. It changes the source IP the target sees; it does not hide the
payload, the account, the browser fingerprint, or the request pattern.

## Teardown

- Stop the local bridge and any browser left running with the proxy flag.
- Leave `~/.x402socks/token` in place if the plan is still live — it is the
  cheapest thing to reuse next session.
- Never copy the token or key into the project you were scraping.
