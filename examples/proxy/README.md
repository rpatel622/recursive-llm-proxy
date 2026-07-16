# Proxy examples

These files support the [quick start](../../docs/quickstart.md).

| File | Purpose |
|---|---|
| `slot_setup.json` | Registers two isolated slots and three workstreams |
| `auto_route.json` | Sends a request through adaptive automatic routing |
| `explicit_route.json` | Bypasses model routing with stable slugs |
| `openai_sdk.py` | Registers the catalog and calls the proxy using the OpenAI Python client |

Run the curl fixtures from the repository root:

```bash
curl -fsS -X PUT http://127.0.0.1:8000/v1/rlm/slots \
  -H 'Authorization: Bearer local-public-key' \
  -H 'Content-Type: application/json' \
  --data @examples/proxy/slot_setup.json

curl -fsS -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H 'Authorization: Bearer local-public-key' \
  -H 'Content-Type: application/json' \
  --data @examples/proxy/auto_route.json
```

Run the SDK example:

```bash
pip install openai httpx
RLM_PROXY_API_KEY='local-public-key' python examples/proxy/openai_sdk.py
```
