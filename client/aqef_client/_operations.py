"""Generated from docs/OPENAPI.json by client/tools/generate_operations.py."""

import httpx

from ._transport import Transport, segment


class Operations(Transport):
    """Named operations exposed by the reference API."""

    def list_teams(
        self,
        *,
        offset: int | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """GET /teams."""
        return self.request(
            "GET",
            "/teams",
            params={
                "offset": offset,
                "limit": limit,
            },
        )

    def create_team(
        self,
        body: object,
    ) -> httpx.Response:
        """POST /teams."""
        return self.request(
            "POST",
            "/teams",
            body=body,
        )

    def list_roles(
        self,
        *,
        offset: int | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """GET /roles."""
        return self.request(
            "GET",
            "/roles",
            params={
                "offset": offset,
                "limit": limit,
            },
        )

    def create_role(
        self,
        body: object,
    ) -> httpx.Response:
        """POST /roles."""
        return self.request(
            "POST",
            "/roles",
            body=body,
        )

    def create_principal(
        self,
        body: object,
    ) -> httpx.Response:
        """POST /principals."""
        return self.request(
            "POST",
            "/principals",
            body=body,
        )

    def get_audit_log(
        self,
        project: str,
        *,
        action: str | None = None,
        principal_id: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/audit."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/audit",
            params={
                "action": action,
                "principal_id": principal_id,
                "offset": offset,
                "limit": limit,
            },
        )

    def list_approvals(
        self,
        project: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/approvals."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/approvals",
            params={
                "offset": offset,
                "limit": limit,
            },
        )

    def list_projects(
        self,
        *,
        offset: int | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """GET /projects."""
        return self.request(
            "GET",
            "/projects",
            params={
                "offset": offset,
                "limit": limit,
            },
        )

    def create_project(
        self,
        body: object,
        *,
        x_approved_by: str | None = None,
        x_external_review_ref: str | None = None,
    ) -> httpx.Response:
        """POST /projects."""
        return self.request(
            "POST",
            "/projects",
            body=body,
            headers={
                "X-Approved-By": x_approved_by,
                "X-External-Review-Ref": x_external_review_ref,
            },
        )

    def get_project(
        self,
        project: str,
    ) -> httpx.Response:
        """GET /projects/{project}."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}",
        )

    def update_project(
        self,
        project: str,
        body: object,
        *,
        x_approved_by: str | None = None,
        x_external_review_ref: str | None = None,
    ) -> httpx.Response:
        """PUT /projects/{project}."""
        return self.request(
            "PUT",
            f"/projects/{segment(project)}",
            body=body,
            headers={
                "X-Approved-By": x_approved_by,
                "X-External-Review-Ref": x_external_review_ref,
            },
        )

    def delete_project(
        self,
        project: str,
        *,
        retain_history: bool | None = None,
    ) -> httpx.Response:
        """DELETE /projects/{project}."""
        return self.request(
            "DELETE",
            f"/projects/{segment(project)}",
            params={
                "retain_history": retain_history,
            },
        )

    def list_environments(
        self,
        project: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/environments."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/environments",
            params={
                "offset": offset,
                "limit": limit,
            },
        )

    def create_environment(
        self,
        project: str,
        body: object,
    ) -> httpx.Response:
        """POST /projects/{project}/environments."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/environments",
            body=body,
        )

    def get_environment(
        self,
        project: str,
        env: str,
    ) -> httpx.Response:
        """GET /projects/{project}/environments/{env}."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/environments/{segment(env)}",
        )

    def update_environment(
        self,
        project: str,
        env: str,
        body: object,
    ) -> httpx.Response:
        """PUT /projects/{project}/environments/{env}."""
        return self.request(
            "PUT",
            f"/projects/{segment(project)}/environments/{segment(env)}",
            body=body,
        )

    def delete_environment(
        self,
        project: str,
        env: str,
    ) -> httpx.Response:
        """DELETE /projects/{project}/environments/{env}."""
        return self.request(
            "DELETE",
            f"/projects/{segment(project)}/environments/{segment(env)}",
        )

    def list_suites(
        self,
        project: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/suites."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/suites",
            params={
                "offset": offset,
                "limit": limit,
            },
        )

    def create_suite(
        self,
        project: str,
        body: object,
        *,
        x_approved_by: str | None = None,
        x_external_review_ref: str | None = None,
    ) -> httpx.Response:
        """POST /projects/{project}/suites."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/suites",
            body=body,
            headers={
                "X-Approved-By": x_approved_by,
                "X-External-Review-Ref": x_external_review_ref,
            },
        )

    def get_suite(
        self,
        project: str,
        suite: str,
    ) -> httpx.Response:
        """GET /projects/{project}/suites/{suite}."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/suites/{segment(suite)}",
        )

    def get_scenario(
        self,
        project: str,
        suite: str,
        scenario: str,
    ) -> httpx.Response:
        """GET /projects/{project}/suites/{suite}/scenarios/{scenario}."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/suites/{segment(suite)}/scenarios/{segment(scenario)}",
        )

    def update_scenario(
        self,
        project: str,
        suite: str,
        scenario: str,
        body: object,
        *,
        x_approved_by: str | None = None,
        x_external_review_ref: str | None = None,
    ) -> httpx.Response:
        """PUT /projects/{project}/suites/{suite}/scenarios/{scenario}."""
        return self.request(
            "PUT",
            f"/projects/{segment(project)}/suites/{segment(suite)}/scenarios/{segment(scenario)}",
            body=body,
            headers={
                "X-Approved-By": x_approved_by,
                "X-External-Review-Ref": x_external_review_ref,
            },
        )

    def delete_scenario(
        self,
        project: str,
        suite: str,
        scenario: str,
        *,
        x_approved_by: str | None = None,
        x_external_review_ref: str | None = None,
    ) -> httpx.Response:
        """DELETE /projects/{project}/suites/{suite}/scenarios/{scenario}."""
        return self.request(
            "DELETE",
            f"/projects/{segment(project)}/suites/{segment(suite)}/scenarios/{segment(scenario)}",
            headers={
                "X-Approved-By": x_approved_by,
                "X-External-Review-Ref": x_external_review_ref,
            },
        )

    def create_scenario(
        self,
        project: str,
        suite: str,
        body: object,
        *,
        x_approved_by: str | None = None,
        x_external_review_ref: str | None = None,
    ) -> httpx.Response:
        """POST /projects/{project}/suites/{suite}/scenarios."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/suites/{segment(suite)}/scenarios",
            body=body,
            headers={
                "X-Approved-By": x_approved_by,
                "X-External-Review-Ref": x_external_review_ref,
            },
        )

    def list_contracts(
        self,
        project: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/contracts."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/contracts",
            params={
                "offset": offset,
                "limit": limit,
            },
        )

    def create_contract(
        self,
        project: str,
        body: object,
        *,
        x_approved_by: str | None = None,
        x_external_review_ref: str | None = None,
    ) -> httpx.Response:
        """POST /projects/{project}/contracts."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/contracts",
            body=body,
            headers={
                "X-Approved-By": x_approved_by,
                "X-External-Review-Ref": x_external_review_ref,
            },
        )

    def get_contract(
        self,
        project: str,
        contract: str,
    ) -> httpx.Response:
        """GET /projects/{project}/contracts/{contract}."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/contracts/{segment(contract)}",
        )

    def update_contract(
        self,
        project: str,
        contract: str,
        body: object,
        *,
        x_approved_by: str | None = None,
        x_external_review_ref: str | None = None,
    ) -> httpx.Response:
        """PUT /projects/{project}/contracts/{contract}."""
        return self.request(
            "PUT",
            f"/projects/{segment(project)}/contracts/{segment(contract)}",
            body=body,
            headers={
                "X-Approved-By": x_approved_by,
                "X-External-Review-Ref": x_external_review_ref,
            },
        )

    def list_datasets(
        self,
        project: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/datasets."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/datasets",
            params={
                "offset": offset,
                "limit": limit,
            },
        )

    def create_dataset(
        self,
        project: str,
        body: object,
    ) -> httpx.Response:
        """POST /projects/{project}/datasets."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/datasets",
            body=body,
        )

    def get_dataset(
        self,
        project: str,
        dataset: str,
        *,
        version: str | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/datasets/{dataset}."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/datasets/{segment(dataset)}",
            params={
                "version": version,
            },
        )

    def get_dataset_rows(
        self,
        project: str,
        dataset: str,
        *,
        version: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/datasets/{dataset}/rows."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/datasets/{segment(dataset)}/rows",
            params={
                "version": version,
                "offset": offset,
                "limit": limit,
            },
        )

    def create_dataset_version(
        self,
        project: str,
        dataset: str,
        body: object,
    ) -> httpx.Response:
        """POST /projects/{project}/datasets/{dataset}/versions."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/datasets/{segment(dataset)}/versions",
            body=body,
        )

    def list_quality_gates(
        self,
        project: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/gates."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/gates",
            params={
                "offset": offset,
                "limit": limit,
            },
        )

    def create_quality_gate(
        self,
        project: str,
        body: object,
        *,
        x_approved_by: str | None = None,
        x_external_review_ref: str | None = None,
    ) -> httpx.Response:
        """POST /projects/{project}/gates."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/gates",
            body=body,
            headers={
                "X-Approved-By": x_approved_by,
                "X-External-Review-Ref": x_external_review_ref,
            },
        )

    def update_quality_gate(
        self,
        project: str,
        gate: str,
        body: object,
        *,
        x_approved_by: str | None = None,
        x_external_review_ref: str | None = None,
    ) -> httpx.Response:
        """PUT /projects/{project}/gates/{gate}."""
        return self.request(
            "PUT",
            f"/projects/{segment(project)}/gates/{segment(gate)}",
            body=body,
            headers={
                "X-Approved-By": x_approved_by,
                "X-External-Review-Ref": x_external_review_ref,
            },
        )

    def trigger_execution(
        self,
        project: str,
        body: object,
    ) -> httpx.Response:
        """POST /projects/{project}/executions."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/executions",
            body=body,
        )

    def list_executions(
        self,
        project: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
        suite: str | None = None,
        environment: str | None = None,
        status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/executions."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/executions",
            params={
                "offset": offset,
                "limit": limit,
                "suite": suite,
                "environment": environment,
                "status": status,
                "date_from": date_from,
                "date_to": date_to,
            },
        )

    def get_execution(
        self,
        project: str,
        execution: str,
    ) -> httpx.Response:
        """GET /projects/{project}/executions/{execution}."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/executions/{segment(execution)}",
        )

    def get_conversation(
        self,
        project: str,
        execution: str,
    ) -> httpx.Response:
        """GET /projects/{project}/executions/{execution}/conversation."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/executions/{segment(execution)}/conversation",
        )

    def list_artifacts(
        self,
        project: str,
        execution: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/executions/{execution}/artifacts."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/executions/{segment(execution)}/artifacts",
            params={
                "offset": offset,
                "limit": limit,
            },
        )

    def list_results(
        self,
        project: str,
        execution: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
        oracle_type: str | None = None,
        verdict: str | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/executions/{execution}/results."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/executions/{segment(execution)}/results",
            params={
                "offset": offset,
                "limit": limit,
                "oracle_type": oracle_type,
                "verdict": verdict,
            },
        )

    def record_admission(
        self,
        project: str,
        body: object,
    ) -> httpx.Response:
        """POST /projects/{project}/admissions."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/admissions",
            body=body,
        )

    def list_admissions(
        self,
        project: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
        oracle: str | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/admissions."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/admissions",
            params={
                "offset": offset,
                "limit": limit,
                "oracle": oracle,
            },
        )

    def register_validator(
        self,
        project: str,
        body: object,
        *,
        x_approved_by: str | None = None,
        x_external_review_ref: str | None = None,
    ) -> httpx.Response:
        """POST /projects/{project}/validators."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/validators",
            body=body,
            headers={
                "X-Approved-By": x_approved_by,
                "X-External-Review-Ref": x_external_review_ref,
            },
        )

    def list_validators(
        self,
        project: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/validators."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/validators",
            params={
                "offset": offset,
                "limit": limit,
            },
        )

    def check_gates(
        self,
        project: str,
        body: object,
    ) -> httpx.Response:
        """POST /projects/{project}/gates/check."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/gates/check",
            body=body,
        )

    def capture_snapshot(
        self,
        project: str,
        body: object,
    ) -> httpx.Response:
        """POST /projects/{project}/snapshots."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/snapshots",
            body=body,
        )

    def list_snapshots(
        self,
        project: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/snapshots."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/snapshots",
            params={
                "offset": offset,
                "limit": limit,
            },
        )

    def generate_report(
        self,
        project: str,
        body: object,
    ) -> httpx.Response:
        """POST /projects/{project}/reports."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/reports",
            body=body,
        )

    def list_reports(
        self,
        project: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/reports."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/reports",
            params={
                "offset": offset,
                "limit": limit,
            },
        )

    def override_gate(
        self,
        project: str,
        gate: str,
        body: object,
    ) -> httpx.Response:
        """POST /projects/{project}/gates/{gate}/override."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/gates/{segment(gate)}/override",
            body=body,
        )

    def approve_baseline(
        self,
        project: str,
        body: object,
    ) -> httpx.Response:
        """POST /projects/{project}/baselines."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/baselines",
            body=body,
        )

    def list_baselines(
        self,
        project: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/baselines."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/baselines",
            params={
                "offset": offset,
                "limit": limit,
            },
        )

    def approve_release_policy(
        self,
        project: str,
        body: object,
    ) -> httpx.Response:
        """POST /projects/{project}/release-policies."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/release-policies",
            body=body,
        )

    def list_release_policies(
        self,
        project: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/release-policies."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/release-policies",
            params={
                "offset": offset,
                "limit": limit,
            },
        )

    def revoke_release_policy(
        self,
        project: str,
        policy: str,
    ) -> httpx.Response:
        """POST /projects/{project}/release-policies/{policy}/revoke."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/release-policies/{segment(policy)}/revoke",
        )

    def record_release(
        self,
        project: str,
        body: object,
    ) -> httpx.Response:
        """POST /projects/{project}/releases."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/releases",
            body=body,
        )

    def list_releases(
        self,
        project: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/releases."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/releases",
            params={
                "offset": offset,
                "limit": limit,
            },
        )

    def review_result(
        self,
        project: str,
        execution: str,
        result: str,
        body: object,
    ) -> httpx.Response:
        """POST /projects/{project}/executions/{execution}/results/{result}/review."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/executions/{segment(execution)}/results/{segment(result)}/review",
            body=body,
        )

    def reassess_result(
        self,
        project: str,
        execution: str,
        result: str,
        body: object,
    ) -> httpx.Response:
        """POST /projects/{project}/executions/{execution}/results/{result}/reassess."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/executions/{segment(execution)}/results/{segment(result)}/reassess",
            body=body,
        )

    def get_snapshot(
        self,
        project: str,
        key: str,
    ) -> httpx.Response:
        """GET /projects/{project}/snapshots/{key}."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/snapshots/{segment(key)}",
        )

    def get_baseline(
        self,
        project: str,
        key: str,
    ) -> httpx.Response:
        """GET /projects/{project}/baselines/{key}."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/baselines/{segment(key)}",
        )

    def get_report(
        self,
        project: str,
        key: str,
    ) -> httpx.Response:
        """GET /projects/{project}/reports/{key}."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/reports/{segment(key)}",
        )

    def get_release(
        self,
        project: str,
        key: str,
    ) -> httpx.Response:
        """GET /projects/{project}/releases/{key}."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/releases/{segment(key)}",
        )

    def get_release_policy(
        self,
        project: str,
        key: str,
    ) -> httpx.Response:
        """GET /projects/{project}/release-policies/{key}."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/release-policies/{segment(key)}",
        )

    def confirm_seeded_control(
        self,
        project: str,
        execution: str,
        scenario: str,
        body: object,
    ) -> httpx.Response:
        """POST /projects/{project}/executions/{execution}/seeded-controls/{scenario}/confirm."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/executions/{segment(execution)}/seeded-controls/{segment(scenario)}/confirm",
            body=body,
        )

    def invalidate_seeded_control(
        self,
        project: str,
        execution: str,
        scenario: str,
        body: object,
    ) -> httpx.Response:
        """POST /projects/{project}/executions/{execution}/seeded-controls/{scenario}/invalidate."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/executions/{segment(execution)}/seeded-controls/{segment(scenario)}/invalidate",
            body=body,
        )

    def record_requalification(
        self,
        project: str,
        body: object,
    ) -> httpx.Response:
        """POST /projects/{project}/requalifications."""
        return self.request(
            "POST",
            f"/projects/{segment(project)}/requalifications",
            body=body,
        )

    def list_requalifications(
        self,
        project: str,
        *,
        offset: int | None = None,
        limit: int | None = None,
    ) -> httpx.Response:
        """GET /projects/{project}/requalifications."""
        return self.request(
            "GET",
            f"/projects/{segment(project)}/requalifications",
            params={
                "offset": offset,
                "limit": limit,
            },
        )

    def health_check(
        self,
    ) -> httpx.Response:
        """GET /healthz."""
        return self.request(
            "GET",
            "/healthz",
        )
