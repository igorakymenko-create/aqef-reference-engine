# Ambiguities Log

This document records points in the AQEF specification (Working Draft 0.41.1) where the text allows more than one reading, following Rule 3 of the Implementer's Brief:
- Pick the more conservative reading (rejects more, blocks more, records more).
- Never decide an ambiguity silently.
- Record: Section, Quotation, Readings seen, Choice and rationale.

---

## 1. Approval Workflow Execution Mechanism for `contract_define`

- **Section:** Volume XII — Governance (§Approval Workflow, §Principals) & Appendix C §C.3, §C.5
- **Quotation:**
  > "Approval Workflow is the single mechanism — a request, review by someone holding an appropriate Role, an explicit approve-or-deny decision, logged for Audit and Traceability... Defining a Contract includes defining or changing a Quality Gate... A `contract_define` applied by a Service Account MUST name the approving Person and reference the external review." (Volume XII)
  > "Minimal Engine and Enterprise Engine... A Minimal Engine's single-click Approval Workflow and an Enterprise Engine's multi-Role review chain are equally conformant realizations of the same Governance requirement" (§10)
  > "`POST /projects/{project}/contracts`: Create a Contract. Governed by Approval Workflow. Permission: `contract_define`." (Appendix C §C.3)
- **Readings seen:**
  1. *Two-phase only:* Every `contract_define` operation MUST first be submitted as a pending Approval request to `/projects/{project}/approvals`, and cannot take effect until a separate approval call is made.
  2. *Direct execution with immediate approval record for Persons; explicit external review reference for Service Accounts:* A Person possessing `contract_define` calling `POST /contracts` or `POST /gates` acts as the approver; the engine verifies their permission, creates an Approval record (`status: approved`, `approved_by: <person_id>`), executes the change, and emits an Audit Log entry. A Service Account calling the endpoint MUST supply `approved_by` (naming a Person) and `external_review_reference`; otherwise the request is rejected.
- **Choice and rationale:** Reading 2 is chosen for the synchronous API, with the strict conservative constraint: if a Service Account attempts `contract_define` without an `approved_by` naming an existing Person and an `external_review_reference`, it is strictly rejected (HTTP 403/422). Furthermore, both an Approval record (in `/approvals`) and an Audit log entry (in `/audit`) are unconditionally recorded for every contract and gate mutation.

---

## 2. Dataset Version Immutability and Re-registration

- **Section:** Volume IV — Dataset Engine (§Versioning) & Appendix B §B.3
- **Quotation:**
  > "Two configurations referencing the same Dataset name + version MUST resolve to identical rows." (Appendix B §B.3)
  > "Every Dataset, regardless of source, MUST be versioned... A Scenario therefore references a Dataset by name and version, `name@version`, never by name alone." (Volume IV)
- **Readings seen:**
  1. *Overwrite allowed if rows match:* A `POST` with the same name and version could check if existing rows are byte-for-byte identical.
  2. *Strict immutability (immutable version key):* Once a Dataset `name@version` is created, any subsequent attempt to POST or register the exact same `name` and `version` is strictly rejected with a conflict (HTTP 409).
- **Choice and rationale:** Reading 2 (Strict immutability). Rejecting any re-creation prevents any race condition or silent divergence, ensuring reproducible Variable Resolution.

---

## 3. Contract Composition Clause Conflict Definition

- **Section:** Volume VII — Quality Contracts (§Contract Composition) & Appendix B §B.3
- **Quotation:**
  > "Two contributed clauses are the same clause only when they declare the same `id`. With identical content they are one clause; with differing content, such as two Confidence thresholds, they are a conflict. A clause without an `id` is never the same clause as another: it is added, and applies alongside whatever else was contributed... a lower level adds clauses but cannot remove or weaken a clause contributed by a higher one."
- **Readings seen:**
  1. *Permit compatible tightening:* A lower level could override a higher-level clause with a stricter threshold (e.g., increasing `confidence_threshold` from 0.7 to 0.8) without being considered a conflict.
  2. *Strict identity required on shared ID:* If two contributed clauses share the same `id`, they MUST be structurally identical across all properties. Any difference (whether looser or tighter) is treated as a composition conflict and rejected.
- **Choice and rationale:** Reading 2 (Strict identity). The spec states: "With identical content they are one clause; with differing content, such as two Confidence thresholds, they are a conflict... silently picking one value would hide exactly the kind of drift Chapter 3 requires a Contract to remain auditable against." Therefore, any difference in a clause with the same `id` is surfaced as an explicit composition conflict error.

---

## 4. Deletion of Project with Historical Data

- **Section:** Appendix C §C.8
- **Quotation:**
  > "`DELETE /projects/{project}` MUST NOT be permitted while the Project has Baselines, Reports, or audit records unless the caller explicitly requests their retention or their deletion is separately, explicitly authorized."
- **Readings seen:**
  1. Query parameter or header flag `force=true`.
  2. Explicit parameter `retain_history=true` or separate authorization permission `audit_delete` / `history_delete`.
- **Choice and rationale:** Conservative approach: By default, `DELETE /projects/{project}` MUST be rejected (HTTP 409 Conflict) if any Baselines, Reports, Snapshots, or Audit records exist. It is only permitted if the query parameter `retain_history=true` is passed (which cascades deletion of active entities while preserving frozen audit/history records) or if an explicit administrative override is passed by a principal holding `project_delete` and `audit_admin`.

---

## 5. Bearer Token Authentication Resolution

- **Section:** Appendix C §C.4 & Volume XII (§Principals)
- **Quotation:**
  > "All API operations MUST be authenticated. The authentication mechanism is implementation-defined (API key, OAuth 2.0, etc.) but MUST resolve to a Principal — a Person or a Service Account with an owning Person — with Team membership and Role assignments (Volume XII — Principals)."
- **Readings seen:**
  1. External OAuth/JWT server.
  2. Bearer token lookup table / database mapping tokens directly to Principal records, each with `kind` (`person` or `service_account`), `team_ids`, and assigned `roles` which map to granular `permissions`.
- **Choice and rationale:** Reading 2. In accordance with BRIEF.md §4 ("A bearer token per Principal is enough. Document how Principals, Teams, Roles, and Permissions are created"), the engine implements a token store where each Bearer token maps to a Principal entity. All requests without a valid `Authorization: Bearer <token>` are rejected with HTTP 401 Unauthorized.
