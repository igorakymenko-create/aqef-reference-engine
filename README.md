# AQEF Reference Engine

A minimal engine that implements the
**[AI Quality Engineering Framework (AQEF)](https://github.com/igorakymenko-create/AQEF)**,
Working Draft [0.41.5](https://github.com/igorakymenko-create/AQEF/tree/0.41.5): an open
specification for testing AI systems, with Quality Contracts, independent Judges,
Confidence, Seeded Controls, Quality Gates, and governed Release Decisions.

**Why it exists.** It shows that the specification can be implemented as written. It is
a feasibility proof, not a product: one process, SQLite, and a plain HTTP interface for
the system under test and its Judges ([docs/PROVIDERS.md](docs/PROVIDERS.md)).

**How it was built.** An AI coding agent wrote it from the specification text alone,
in eleven slices, one tag each (`slice-1` to `slice-11`). The agent never saw the AQEF
Conformance Test Specification. Every unclear point in the text was recorded in
[docs/AMBIGUITIES.md](docs/AMBIGUITIES.md), not decided silently. After each slice, the
project owner ran the Conformance Tests against it. Engine defects came back here; a
point the specification left unclear went back to the specification, as a new release.

**Conformance.** The engine claims AQEF Conformance at 0.41.5 for the core and for
`human_review`, `multi_judge`, and `seeded_controls`. See:
- the [Conformance Statement](docs/CONFORMANCE-STATEMENT.md): its scope, its
  implementation choices, and the SHOULDs it does not follow;
- the [normative review](docs/CONFORMANCE-REVIEW.md): rule by rule, where each MUST is
  met, and the verification work that remains.

The external run of the AQEF Conformance Tests, Working Draft 9, found no failure: 171
passed, 32 were not applicable to the claimed capabilities, and 9 await manual review.
The tests are published with the specification, in its `conformance-tests/` folder and
as a PDF on each release.

OpenAPI ([docs/OPENAPI.json](docs/OPENAPI.json)) is published as API documentation,
not as an AQEF JSON Schema artifact.

**License.** Apache 2.0 ([LICENSE](LICENSE)). The AQEF specification itself is CC BY
4.0, in its own repository.

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
