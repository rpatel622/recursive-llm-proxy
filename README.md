# recursive-llm-proxy

An OpenAI-compatible proxy and local administration UI for Recursive Language Models.

This repository is a fork of [`grishahq/recursive-llm`](https://github.com/grishahq/recursive-llm). It preserves the upstream Python RLM library and adds a deployable public API, context-slot routing, workstream separation, monitoring, and a self-configuring Gradio control surface.

## What this fork adds

```text
application
  <-> public OpenAI-compatible API
  <-> rolling ingestion for oversized messages
  <-> slot/workstream router
  <-> selected isolated context
  <-> recursive-llm RLM runtime
  <-> private OpenAI-compatible API
  <-> llama-server or another provider
```

- OpenAI-compatible `/v1/chat/completions` and `/v1/models`
- Private OpenAI-compatible model boundary through LiteLLM
- Rolling-window preprocessing for giant message dumps
- Natural-boundary chunking, semantic metadata, and actual-request extraction
- Isolated context slots with named workstreams
- Automatic routing with adaptive recent-turn expansion
- Explicit slot/workstream slug overrides
- Clarification responses when routing remains ambiguous
- Process-local request metrics and recent-request monitoring
- Optional Gradio UI for configuration, proxy lifecycle, slot management, testing, and monitoring
- The original `rlm.RLM` Python library and recursive REPL execution model

## Status and scope

This fork is intended for a trusted single operator running local or private models. Slots are context-isolation boundaries, not security boundaries. The slot catalog and metrics are currently process-local and reset when the proxy restarts.

The upstream RLM implementation and paper attribution remain unchanged. Fork-specific proxy and UI code lives under `src/rlm_proxy`.

## Fastest start

Requirements:

- Python 3.10 or newer for the Gradio UI
- A running private OpenAI-compatible model endpoint, such as `llama-server`

```bash
git clone https://github.com/rpatel622/recursive-llm-proxy.git
cd recursive-llm-proxy
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[proxy,ui]'
rlm-proxy-ui
```

Open `http://127.0.0.1:7860`.

From the UI, configure:

- public proxy host and port
- public bearer key
- private OpenAI-compatible API URL and key
- root and recursive model names
- RLM depth and iteration limits

Then press **Start / restart proxy**.

Default endpoints:

```text
Gradio UI:    http://127.0.0.1:7860
Public proxy: http://127.0.0.1:8000
Private API:  http://127.0.0.1:8080/v1
Models:       openai/local
```

The UI does not launch `llama-server`; the private endpoint must already be running.

## Start without the UI

```bash
python -m pip install -e '.[proxy]'

export RLM_PROXY_PUBLIC_API_KEY='local-public-key'
export RLM_PROXY_PRIVATE_API_BASE='http://127.0.0.1:8080/v1'
export RLM_PROXY_PRIVATE_API_KEY='not-needed'
export RLM_PROXY_MODEL='openai/local'
export RLM_PROXY_RECURSIVE_MODEL='openai/local'

rlm-proxy --host 127.0.0.1 --port 8000
```

## OpenAI client example

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:8000/v1",
    api_key="local-public-key",
)

response = client.chat.completions.create(
    model="rlm",
    messages=[
        {"role": "user", "content": "What is the production rollback plan?"}
    ],
    extra_body={
        "rlm": {
            "routing": {
                "mode": "auto",
                "initial_turn_count": 4,
                "max_turn_count": 64,
                "allow_multi_workstream": True,
                "allow_cross_slot": False,
            }
        }
    },
)

print(response.choices[0].message.content)
```

## Giant message dumps

When the final user message is at least 24,000 characters, the proxy automatically:

1. splits it at paragraphs, headings, lists, and sentence boundaries;
2. processes bounded rolling windows instead of repeatedly prefilling the full dump;
3. creates titles, summaries, topics, entities, facts, and boundary metadata;
4. extracts the actual user request;
5. sends only that extracted request to slot routing and the root RLM prompt;
6. retains exact raw chunk text in the RLM external context for targeted REPL search.

The behavior is configurable under `rlm.ingestion` and can be disabled per request. See [Rolling ingestion](docs/rolling-ingestion.md).

## Slot and workstream model

A slot is an isolated context domain. A workstream is a separate history inside a slot.

```text
slot: engineering
  workstream: deployment-prod
  workstream: deployment-staging

slot: legal
  workstream: vendor-contract
```

Automatic routing can combine multiple workstreams within one slot. Cross-slot routing is disabled by default. Explicit slugs always override automatic routing.

Register or replace the catalog with:

```http
PUT /v1/rlm/slots
```

Inspect it with:

```http
GET /v1/rlm/slots
```

## Monitoring

The proxy exposes authenticated process-local metrics:

```http
GET /v1/rlm/metrics
```

Metrics include request totals, failures, clarifications, latency, token counts, slot/workstream counts, and recent request routing records. Prompts, selected context, and generated answers are not retained in metrics.

## Original Python RLM library

The upstream library remains available directly:

```python
from rlm import RLM

rlm = RLM(
    model="openai/local",
    api_base="http://127.0.0.1:8080/v1",
    api_key="not-needed",
    max_depth=2,
)

answer = rlm.complete(
    query="Summarize the unresolved risks",
    context=long_document,
)
```

RLM keeps long context in a restricted Python REPL and lets the model inspect, search, partition, and recursively process relevant portions.

## Documentation

- [Five-minute quick start](docs/quickstart.md)
- [Gradio administration UI](docs/admin-ui.md)
- [Proxy API reference](docs/api.md)
- [Rolling ingestion](docs/rolling-ingestion.md)
- [Slot and workstream routing](docs/slot-routing.md)
- [Architecture](docs/architecture.md)
- [Detailed proxy reference](docs/openai-proxy.md)
- [Runnable proxy examples](examples/proxy/README.md)

## Development and verification

```bash
python -m pip install -e '.[proxy,ui,dev]'
pytest
mypy src/rlm
ruff check src tests benchmarks examples
black --check src tests examples benchmarks
python -m build
```

The core library supports Python 3.9 and newer. Current Gradio releases require Python 3.10 or newer.

## Upstream and attribution

This fork is based on [`grishahq/recursive-llm`](https://github.com/grishahq/recursive-llm), which implements the Recursive Language Models approach described by Alex L. Zhang, Tim Kraska, and Omar Khattab.

- [RLM paper](https://arxiv.org/abs/2512.24601)
- [Official research implementation](https://github.com/alexzhang13/rlm)
- [Upstream Python implementation](https://github.com/grishahq/recursive-llm)

Fork-specific proxy and UI changes are maintained in this repository. Upstream library issues should be checked against the upstream project before filing here.

## License

MIT. See [LICENSE](LICENSE).
