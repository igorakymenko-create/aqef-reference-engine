# AQEF Reference Engine

A reference implementation of the **[AI Quality Engineering Framework (AQEF)](https://github.com/igorakymenko-create/AQEF)**, Working Draft 0.41.1.

The engine's purpose is to demonstrate that the AQEF specification can be implemented as written, adhering strictly to its normative rules, schema definitions, and REST API surface.

## Completed Slices

- [x] **Slice 1: Foundation and Definition**
  - Principals, Teams, Roles, Permissions, authentication, audit log
  - Projects, Environments, Suites, Scenarios
  - Static Datasets with versioning and immutability
  - Quality Contracts with additive composition and conflict detection
  - Quality Gates with basis requirements and name uniqueness
  - Approval Workflow governing contract and quality gate changes
- [x] **Slice 2: Execution and Evidence**
  - Suite × Environment batches, static row expansion, isolated sequential/parallel runs
  - Deterministic Variables/Context, multi-turn Conversations, captured Artifacts
  - Infrastructure retries, whole-execution timeouts, durable frozen Evidence
  - HTTP subject provider; startup mapping and wire contract in [docs/PROVIDERS.md](docs/PROVIDERS.md)
- [x] **Slice 3: Assessment**
  - Deterministic built-in and registered Custom Validators with composition/veto
  - HTTP Single Judge, Confidence, immutable Results and Admission records
- [ ] **Slice 4: Decision and Release**
- [ ] **Slice 5: Scoped Capabilities**
- [ ] **Slice 6: Conformance Statement**

## Installation and Usage

The engine is built on Python 3.12, FastAPI, SQLite, and pytest.

For installation, bootstrapping, running the API server, authentication details, and HTTP status codes, see **[docs/API.md](docs/API.md)**.

### Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run test suite
pytest

# Start the REST API server
uvicorn engine.main:app --host 127.0.0.1 --port 8000
```
