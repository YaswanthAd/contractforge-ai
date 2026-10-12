# ContractForge

**An AI-assisted data-contract lab that makes migrations prove themselves.**

Python 3.11+ · FastAPI · SQLite · optional local Ollama · MIT

An AI-generated migration can look correct while silently truncating money, overwriting an identity, or rejecting international orders. A credible migration needs executable counterexamples, not a persuasive explanation.

ContractForge is a working local portfolio application with a browser workbench, typed HTTP API, saved runs, repeatable synthetic scenarios, and a real Ollama adapter. The default evidence engine runs without a model or API key. Select **Local AI / Ollama** to enable model inference.

## Architecture

The main diagram is the **proposed AWS deployment**: service icons, network boundaries, and labeled data and deployment paths. The cloud services are a design target; this release runs locally.

![ContractForge AWS deployment blueprint](docs/assets/architecture.png)

[Full-resolution PNG](docs/assets/architecture.png) · [Editable cloud diagram](docs/assets/architecture.drawio) · [Cloud design and implementation gaps](docs/CLOUD_DESIGN.md)

The [runnable implementation diagram](docs/assets/implementation.png) maps the actual FastAPI, Python engine, SQLite, and optional Ollama components. See the [low-level design](docs/LLD.md) for contracts, algorithms, and failure behavior, and the [layered component view](docs/assets/layers.png) for module boundaries.

Open the `.drawio` files in [diagrams.net](https://app.diagrams.net/) to edit individual service icons, labels, and connectors. The repository includes SVG and PNG exports; [diagram sources and icon attribution](docs/assets/README.md) explain how to reproduce them.

## Why this project

- **A tiny migration language:** `rename`, `cast`, and unit-aware `scale`; no generated Python or SQL is executed.
- **Business-value checks:** preserve declared semantic identities and normalize cents/dollars before comparing money.
- **Counterexample replay:** test every supplied event against source and target contracts; retain the original when rejected.
- **Loss-aware conversions:** fractional values cannot be silently cast to integers; renames cannot overwrite an existing field.
- **An honest release gate:** report rejection rate against an explicit threshold and scope the result to the replayed sample.

## Run in two minutes

From this repository directory:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m uvicorn contractforge.api:app --host 127.0.0.1 --port 8012
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1` instead.

Open **http://127.0.0.1:8012**. Select a scenario, inspect the results, open the event replay, and export the saved report. **Request JSON** lets you edit the inputs; **Import JSON** accepts your own request.

![ContractForge running workbench](docs/assets/workbench.png)

### Optional local AI

Install [Ollama](https://ollama.com/), start it, and pull a model:

```bash
ollama pull llama3.2
export OLLAMA_URL=http://127.0.0.1:11434
export OLLAMA_MODEL=llama3.2
```

Then launch the app from that same terminal and select **Local AI / Ollama**. Model availability and hardware requirements depend on your machine. The app sends supplied contracts and up to 20 sample events to that configured endpoint. There is no cloud API key. Invalid or unavailable AI output falls back to the evidence engine, with a visible status.

The adapter uses Ollama's [structured-output API](https://docs.ollama.com/capabilities/structured-outputs). Schema and domain checks run again after the response. This validates the plan structure; actual events still determine the replay gate.

### Docker

```bash
docker compose up --build
```

Compose binds the app to localhost and persists SQLite in a named volume. It uses `host.docker.internal:11434` for an Ollama process on the host. Docker configuration is supplied; container execution was not tested in the authoring environment.

## Reproduce the results

```bash
python -m pytest -q
python scripts/evaluate.py
```

The evaluation script asserts expected outcomes and writes [evaluation.json](docs/evaluation.json). These are small, designed synthetic scenarios, not a production benchmark or an LLM quality study. See [validation scope](docs/VALIDATION.md).

| Scenario | Accepted | Quarantined | Default gate |
| --- | ---: | ---: | --- |
| Explicit renames + cents to dollars | 8 | 0 | Pass |
| Fractional dollars narrowed to integer | 3 | 5 | Block |
| Country enum narrowed to US/CA | 6 | 2 | Block |

![Lossy conversion counterexamples](docs/assets/counterexample.png)

## API and CLI

```bash
curl -X POST http://127.0.0.1:8012/api/replays \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-001' \
  --data-binary @examples/01-safe-migration.json

python -m contractforge examples/01-safe-migration.json
```

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Process health |
| `GET /api/scenarios` | Included fixture catalog |
| `GET /api/scenarios/{id}` | Full fixture request |
| `POST /api/replays` | Validate, analyze and save a run |
| `GET /api/replays` | Latest 30 run IDs and timestamps |
| `GET /api/replays/{id}` | Full saved report |
| `GET /openapi.json` | Generated OpenAPI contract |

An `Idempotency-Key` retry with the same normalized request returns the same persisted run. Reusing the key for different input returns `409`. CLI output is ephemeral JSON; it does not write the run database.

## Design decisions and scope

- **One service first.** Domain logic is pure and separate from transport, persistence, and model I/O. A queue and multiple services would add operating cost without improving this bounded demo.
- **SQLite WAL.** Useful for reproducible local runs; not a claim of distributed durability or multi-tenant isolation.
- **No paid infrastructure required.** Evidence mode uses no model; local inference uses your own hardware.
- **Synthetic data only.** No employer logs, schemas, credentials, or business information are included.
- **Advisory behavior.** A replay never deploys a migration or changes a broker/warehouse.

This is a local development release. Before internet exposure, add real identity and authorization, rate limiting, worker isolation, TLS, data retention controls, and operational monitoring. `APP_TOKEN` is a small optional local API guard, not multi-tenant authentication. Production connectors, scheduled ingestion, managed hosting, and live LLM quality evaluation are roadmap items.

## Explore the engineering

- [AWS deployment blueprint and migration plan](docs/CLOUD_DESIGN.md)
- [Low-level design, data model, algorithms and failure semantics](docs/LLD.md)
- [Validation record and explicit limitations](docs/VALIDATION.md)
- [Demo script and LinkedIn showcase notes](docs/SHOWCASE.md)
- [Source scenarios](examples/)
- [Tests](tests/)

Created for [Yaswanth Adari](https://github.com/YaswanthAd) · [MIT license](LICENSE) · [Third-party icon notices](docs/assets/icons/ATTRIBUTION.md)

## Companion project

Explore [SignalLedger](https://github.com/YaswanthAd/signalledger-ai) for the other half of this AI and data-engineering portfolio.
