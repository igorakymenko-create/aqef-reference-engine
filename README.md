# AQEF Reference Engine

A reference implementation of the **[AI Quality Engineering Framework (AQEF)](https://github.com/igorakymenko-create/AQEF/tree/0.41.5)**, Working Draft 0.41.5.

The engine claims **AQEF Conformance at 0.41.5** for Human Review, Multi Judge and
Seeded Controls, with the core implicit. The [Conformance Statement](docs/CONFORMANCE-STATEMENT.md)
declares the scope, implementation choices, skipped SHOULDs and owner-reported external
evidence. The [normative review](docs/CONFORMANCE-REVIEW.md) lists known verification
work separately; no classification-(a) implementation finding remains.

OpenAPI is published as API documentation, not as an AQEF JSON Schema artifact.

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
  - Infrastructure retries, subject collection timeouts, durable frozen Evidence
  - HTTP subject provider; startup mapping and wire contract in [docs/PROVIDERS.md](docs/PROVIDERS.md)
- [x] **Slice 3: Assessment**
  - Deterministic built-in and registered Custom Validators with composition/veto
  - HTTP Single Judge, Confidence, immutable Results and Admission records
- [x] **Slice 4: Decision and Release**
  - Result resolution, weighted aggregation/Basis, Gates and exact-result overrides
  - Frozen Snapshots/Reports/Baselines, staleness and regression comparisons
  - Governed Release Decisions and standing Service Account Release Policies
- [x] **Slice 5: Scoped Capabilities**
  - Human Review routing/completion, Multi Judge consensus and quorum
  - Confirmed Seeded Controls, invalidation, halt_run and fresh-control Requalification
- [x] **Slice 6: Conformance Statement**
  - Specification rule ledger with implementation/test references and explicit findings
  - Scope, implementation choices, deliberate SHOULD deviations and known gaps
- [x] **Slice 7: Working Draft 0.41.3**
  - Dimension Gate coverage at load/change and uncomputable aggregate reasons
  - Schema/Custom Validator clarifications confirmed; pre-run SHOULD deviations documented
- [x] **Slice 8: Audit and scope corrections**
  - Mutation-only audit history and versioned base Dataset resolution
  - Nonblocking pre-run Suite/Gate warnings; identity and timeout findings clarified

- [x] **Slice 9: Working Draft 0.41.4**
  - Explicit atomic administrative Permissions; no Project/Suite Team bindings
  - Strict policy composition, source clause weights and rejection of unoffered mechanisms
  - Synchronous triggering and audit clarified; primitive schemas tightened

- [x] **Slice 10: Input schemas and final claim review**
  - Reject typed optional nulls and unknown governance keys; migrate live definitions
  - Preserve free JSON/frozen history; document full PUT omission form
  - Separate implementation gaps from verification and cite owner-reported external evidence

- [x] **Slice 11: Working Draft 0.41.5 and Conformance claim**
  - Validate the complete resulting Project on every configuration route and startup
  - Confirm approved Contract changes; close artifact/rationale findings under 0.41.5
  - Claim scoped Conformance with external evidence, verification work and skipped SHOULDs

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
