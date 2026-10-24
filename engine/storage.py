"""Storage layer backed by SQLite for AQEF Reference Engine.

References:
- BRIEF.md §4 (Technology: SQLite)
- Appendix C §C.1–§C.6, §C.8 (Resources and Deletion referential integrity)
- Volume XII — Governance (§Audit, §Traceability, §Approval Workflow)
"""

import json
import sqlite3
import uuid
from threading import RLock
from functools import wraps
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from engine.models.contract import Contract
from engine.models.dataset import Dataset, Row
from engine.models.environment import Environment
from engine.models.gate import QualityGate
from engine.models.principal import (
    ApprovalRecord,
    ApprovalStatus,
    AuditLogEntry,
    Principal,
    PrincipalKind,
    Role,
    Team,
)
from engine.models.project import Project
from engine.models.scenario import Scenario
from engine.models.suite import Suite


class StorageConflictError(Exception):
    """Raised when an operation violates uniqueness, immutability, or referential integrity."""
    pass


class StorageNotFoundError(Exception):
    """Raised when a requested resource does not exist."""
    pass


def synchronized(method):
    @wraps(method)
    def locked(self, *args, **kwargs):
        with self.config_lock:
            return method(self, *args, **kwargs)
    return locked


class Storage:
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.config_lock = RLock()
        self._shared_conn: Optional[sqlite3.Connection] = None
        if self.db_path == ":memory:":
            mem_name = f"aqef_mem_{uuid.uuid4().hex}"
            self._shared_conn = sqlite3.connect(
                f"file:{mem_name}?mode=memory&cache=shared",
                uri=True,
                check_same_thread=False,
            )
            self._shared_conn.row_factory = sqlite3.Row
            self._shared_conn.execute("PRAGMA foreign_keys = ON")
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._shared_conn is not None:
            return self._shared_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS execution_batches (
                id TEXT PRIMARY KEY, project_name TEXT NOT NULL, data_json TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS decision_records (
                kind TEXT NOT NULL, id TEXT NOT NULL, project_name TEXT NOT NULL,
                data_json TEXT NOT NULL, PRIMARY KEY(kind, id))""")
            conn.execute("CREATE TABLE IF NOT EXISTS result_links (previous TEXT PRIMARY KEY, following TEXT UNIQUE NOT NULL)")
            # Frozen runtime history deliberately has no cascade to live configuration.
            conn.execute("""CREATE TABLE IF NOT EXISTS executions (
                id TEXT PRIMARY KEY, project_name TEXT NOT NULL, data_json TEXT NOT NULL
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS assessment_results (
                id TEXT PRIMARY KEY, project_name TEXT NOT NULL, execution_id TEXT NOT NULL,
                data_json TEXT NOT NULL)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS custom_validators (
                project_name TEXT NOT NULL, name TEXT NOT NULL, version TEXT NOT NULL,
                data_json TEXT NOT NULL, PRIMARY KEY (project_name, name, version))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS admissions (
                id TEXT PRIMARY KEY, project_name TEXT NOT NULL, oracle TEXT NOT NULL,
                data_json TEXT NOT NULL)""")
            # Teams, Roles, Principals, Auth Tokens
            conn.execute("""
                CREATE TABLE IF NOT EXISTS teams (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS roles (
                    name TEXT PRIMARY KEY,
                    permissions_json TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS principals (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    email TEXT,
                    team_ids_json TEXT NOT NULL,
                    roles_json TEXT NOT NULL,
                    owner_person_id TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS auth_tokens (
                    token TEXT PRIMARY KEY,
                    principal_id TEXT NOT NULL,
                    FOREIGN KEY(principal_id) REFERENCES principals(id) ON DELETE CASCADE
                )
            """)

            # Projects, Environments, Suites, Scenarios
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    name TEXT PRIMARY KEY,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS environments (
                    project_name TEXT NOT NULL,
                    name TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    PRIMARY KEY (project_name, name),
                    FOREIGN KEY(project_name) REFERENCES projects(name) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS suites (
                    project_name TEXT NOT NULL,
                    name TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    PRIMARY KEY (project_name, name),
                    FOREIGN KEY(project_name) REFERENCES projects(name) ON DELETE CASCADE
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scenarios (
                    project_name TEXT NOT NULL,
                    suite_name TEXT NOT NULL,
                    name TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    PRIMARY KEY (project_name, suite_name, name),
                    FOREIGN KEY(project_name, suite_name) REFERENCES suites(project_name, name) ON DELETE CASCADE
                )
            """)

            # Datasets (Versioned)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS datasets (
                    project_name TEXT NOT NULL,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (project_name, name, version),
                    FOREIGN KEY(project_name) REFERENCES projects(name) ON DELETE CASCADE
                )
            """)

            # Reusable Contracts
            conn.execute("""
                CREATE TABLE IF NOT EXISTS contracts (
                    project_name TEXT NOT NULL,
                    name TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    PRIMARY KEY (project_name, name),
                    FOREIGN KEY(project_name) REFERENCES projects(name) ON DELETE CASCADE
                )
            """)

            # Quality Gates
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quality_gates (
                    project_name TEXT NOT NULL,
                    name TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    PRIMARY KEY (project_name, name),
                    FOREIGN KEY(project_name) REFERENCES projects(name) ON DELETE CASCADE
                )
            """)

            # Approvals and Audit
            conn.execute("""
                CREATE TABLE IF NOT EXISTS approvals (
                    id TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_resource TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    approved_by TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    external_review_reference TEXT,
                    details_json TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    principal_id TEXT NOT NULL,
                    principal_kind TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    details_json TEXT NOT NULL
                )
            """)

            # Reference tracking tables for Baselines, Snapshots, Reports (for referential integrity)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS baselines (
                    id TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    environment_name TEXT NOT NULL,
                    dataset_ref TEXT,
                    contract_ref TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    config_json TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    generated_at TEXT NOT NULL
                )
            """)

    def save_executions(self, records, batch=None):
        with self._get_connection() as conn:
            if batch is not None:
                conn.execute("INSERT INTO execution_batches VALUES (?, ?, ?)",
                             (batch["id"], batch["project"], json.dumps(batch)))
            conn.executemany("INSERT INTO executions VALUES (?, ?, ?)",
                             [(r["id"], r["project"], json.dumps(r)) for r in records])

    def get_batch(self, project, identifier):
        with self._get_connection() as conn:
            row = conn.execute("SELECT data_json FROM execution_batches WHERE project_name = ? AND id = ?",
                               (project, identifier)).fetchone()
            return json.loads(row[0]) if row else None

    def update_execution(self, record):
        with self._get_connection() as conn:
            existing = conn.execute("SELECT data_json FROM executions WHERE id = ?", (record["id"],)).fetchone()
            if not existing or json.loads(existing["data_json"])["status"] not in ("queued", "running"):
                raise StorageConflictError("Completed Execution is immutable")
            conn.execute("UPDATE executions SET data_json = ? WHERE id = ?",
                         (json.dumps(record), record["id"]))

    def get_execution(self, project_name, execution_id):
        with self._get_connection() as conn:
            row = conn.execute("SELECT data_json FROM executions WHERE project_name = ? AND id = ?",
                               (project_name, execution_id)).fetchone()
            return json.loads(row["data_json"]) if row else None

    def list_executions(self, project_name):
        with self._get_connection() as conn:
            return [json.loads(row["data_json"]) for row in conn.execute(
                "SELECT data_json FROM executions WHERE project_name = ? ORDER BY rowid", (project_name,))]

    @synchronized
    def append_result(self, project_name, result):
        from engine.models.assessment import Result
        validated = Result.model_validate(result)
        data = validated.model_dump(mode="json")
        for field in ("assertions", "resolves", "panel"):
            if data[field] is None:
                del data[field]
        with self._get_connection() as conn:
            try:
                if data.get("resolves"):
                    previous = conn.execute("SELECT data_json FROM assessment_results WHERE id = ? AND project_name = ?",
                                            (data["resolves"], project_name)).fetchone()
                    if not previous:
                        raise StorageConflictError("Resolution target not found")
                    previous = json.loads(previous[0])
                    from engine.scoped import invalidators
                    if (previous["execution"], previous["clause"]) != (data["execution"], data["clause"]) or (
                        previous["disposition"] == "actionable" and not invalidators(self, project_name, previous)):
                        raise StorageConflictError("Only a non-actionable Result for the same execution/clause may be resolved")
                    conn.execute("INSERT INTO result_links VALUES (?, ?)", (data["resolves"], data["id"]))
                conn.execute("INSERT INTO assessment_results VALUES (?, ?, ?, ?)",
                             (data["id"], project_name, data["execution"], json.dumps(data)))
            except sqlite3.IntegrityError as exc:
                raise StorageConflictError("Result is immutable") from exc
        return data

    @synchronized
    def complete_review(self, project_name, data):
        from engine.models.assessment import Result
        Result.model_validate(data)
        with self._get_connection() as conn:
            old = conn.execute("SELECT data_json FROM assessment_results WHERE id = ? AND project_name = ?",
                               (data["id"], project_name)).fetchone()
            if not old or json.loads(old[0])["disposition"] != "awaiting_review":
                raise StorageConflictError("Review has already completed")
            if json.loads(old[0])["recorded_at"] != data["recorded_at"]:
                raise StorageConflictError("Review must preserve recorded_at")
            conn.execute("UPDATE assessment_results SET data_json = ? WHERE id = ?", (json.dumps(data), data["id"]))
        return data

    @synchronized
    def save_decision(self, kind, project_name, data):
        with self._get_connection() as conn:
            try:
                conn.execute("INSERT INTO decision_records VALUES (?, ?, ?, ?)",
                             (kind, data["id"], project_name, json.dumps(data)))
            except sqlite3.IntegrityError as exc:
                raise StorageConflictError(f"{kind} record already exists and is immutable") from exc
            if kind == "report":
                conn.execute("INSERT INTO reports VALUES (?, ?, ?)", (data["id"], project_name, data["generated_at"]))
            elif kind == "snapshot":
                conn.execute("INSERT INTO snapshots VALUES (?, ?, ?, ?)",
                             (data["id"], project_name, data["captured_at"], json.dumps(data)))
            elif kind == "baseline":
                conn.execute("INSERT INTO baselines VALUES (?, ?, ?, ?, ?)",
                             (data["id"], project_name, data["environment"], data.get("dataset"), None))
        return data

    def decision_records(self, kind, project_name):
        with self._get_connection() as conn:
            return [json.loads(r[0]) for r in conn.execute(
                "SELECT data_json FROM decision_records WHERE kind = ? AND project_name = ? ORDER BY rowid", (kind, project_name))]

    def decision_record(self, kind, project_name, identifier):
        with self._get_connection() as conn:
            row = conn.execute("SELECT data_json FROM decision_records WHERE kind = ? AND project_name = ? AND id = ?",
                               (kind, project_name, identifier)).fetchone()
            return json.loads(row[0]) if row else None

    def list_results(self, project_name, execution_id):
        with self._get_connection() as conn:
            return [json.loads(row[0]) for row in conn.execute(
                "SELECT data_json FROM assessment_results WHERE project_name = ? AND execution_id = ? ORDER BY rowid",
                (project_name, execution_id))]

    def create_custom_validator(self, project_name, definition):
        with self._get_connection() as conn:
            try:
                conn.execute("INSERT INTO custom_validators VALUES (?, ?, ?, ?)",
                             (project_name, definition["name"], definition["version"], json.dumps(definition)))
            except sqlite3.IntegrityError as exc:
                raise StorageConflictError("Custom Validator name@version is immutable") from exc
        return definition

    def list_custom_validators(self, project_name):
        with self._get_connection() as conn:
            return [json.loads(row[0]) for row in conn.execute(
                "SELECT data_json FROM custom_validators WHERE project_name = ? ORDER BY rowid", (project_name,))]

    @synchronized
    def append_admission(self, project_name, data):
        with self._get_connection() as conn:
            try:
                conn.execute("INSERT INTO admissions VALUES (?, ?, ?, ?)",
                             (data["id"], project_name, data["oracle"], json.dumps(data)))
            except sqlite3.IntegrityError as exc:
                raise StorageConflictError("Admission is immutable") from exc
        return data

    def list_admissions(self, project_name):
        with self._get_connection() as conn:
            return [json.loads(row[0]) for row in conn.execute(
                "SELECT data_json FROM admissions WHERE project_name = ? ORDER BY rowid", (project_name,))]

    def is_admitted(self, project_name, oracle):
        try:configuration=json.loads(oracle)
        except (ValueError,TypeError):configuration={}
        if isinstance(configuration,dict) and configuration.get("type")=="multi_judge":
            from engine.assessment import judge_identity
            panel=configuration["configuration"]
            judges=panel.get("judges") or [panel["judge"]]
            return all(self.is_admitted(project_name,judge_identity({"judge":j,"criteria":configuration["criteria"]})) for j in judges)
        records = [r for r in self.list_admissions(project_name) if r["oracle"] == oracle]
        return bool(records and records[-1]["admitted"])

    # ---------------- Principals, Teams, Roles ----------------

    def create_team(self, team: Team) -> Team:
        with self._get_connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO teams (id, name, description) VALUES (?, ?, ?)",
                    (team.id, team.name, team.description),
                )
            except sqlite3.IntegrityError as e:
                raise StorageConflictError(f"Team '{team.id}' already exists") from e
        return team

    def list_teams(self) -> List[Team]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT id, name, description FROM teams ORDER BY id")
            return [Team(id=row["id"], name=row["name"], description=row["description"]) for row in cursor]

    def create_role(self, role: Role) -> Role:
        with self._get_connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO roles (name, permissions_json) VALUES (?, ?)",
                    (role.name, json.dumps(role.permissions)),
                )
            except sqlite3.IntegrityError as e:
                raise StorageConflictError(f"Role '{role.name}' already exists") from e
        return role

    def list_roles(self) -> List[Role]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT name, permissions_json FROM roles ORDER BY name")
            return [Role(name=row["name"], permissions=json.loads(row["permissions_json"])) for row in cursor]

    def get_role(self, name: str) -> Optional[Role]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT name, permissions_json FROM roles WHERE name = ?", (name,)).fetchone()
            if not row:
                return None
            return Role(name=row["name"], permissions=json.loads(row["permissions_json"]))

    def create_principal(self, principal: Principal, token: Optional[str] = None) -> Principal:
        if principal.kind == PrincipalKind.SERVICE_ACCOUNT:
            owner = self.get_principal(principal.owner_person_id)
            if owner is None or owner.kind != PrincipalKind.PERSON:
                raise StorageConflictError("owner_person_id must name an existing Person")
        with self._get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO principals (id, kind, name, email, team_ids_json, roles_json, owner_person_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        principal.id,
                        principal.kind.value,
                        principal.name,
                        principal.email,
                        json.dumps(principal.team_ids),
                        json.dumps(principal.roles),
                        principal.owner_person_id,
                    ),
                )
                if token:
                    conn.execute(
                        "INSERT INTO auth_tokens (token, principal_id) VALUES (?, ?)",
                        (token, principal.id),
                    )
            except sqlite3.IntegrityError as e:
                raise StorageConflictError(f"Principal '{principal.id}' or token already exists") from e
        return principal

    def get_principal_by_token(self, token: str) -> Optional[Principal]:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT p.id, p.kind, p.name, p.email, p.team_ids_json, p.roles_json, p.owner_person_id
                FROM principals p
                JOIN auth_tokens t ON p.id = t.principal_id
                WHERE t.token = ?
                """,
                (token,),
            ).fetchone()
            if not row:
                return None
            return Principal(
                id=row["id"],
                kind=PrincipalKind(row["kind"]),
                name=row["name"],
                email=row["email"],
                team_ids=json.loads(row["team_ids_json"]),
                roles=json.loads(row["roles_json"]),
                owner_person_id=row["owner_person_id"],
            )

    def get_principal(self, principal_id: str) -> Optional[Principal]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, kind, name, email, team_ids_json, roles_json, owner_person_id FROM principals WHERE id = ?",
                (principal_id,),
            ).fetchone()
            if not row:
                return None
            return Principal(
                id=row["id"],
                kind=PrincipalKind(row["kind"]),
                name=row["name"],
                email=row["email"],
                team_ids=json.loads(row["team_ids_json"]),
                roles=json.loads(row["roles_json"]),
                owner_person_id=row["owner_person_id"],
            )

    # ---------------- Projects ----------------

    @synchronized
    def create_project(self, project: Project) -> Project:
        with self._get_connection() as conn:
            now_iso = datetime.now(timezone.utc).isoformat()
            try:
                conn.execute(
                    "INSERT INTO projects (name, data_json, created_at) VALUES (?, ?, ?)",
                    (project.name, project.model_dump_json(), now_iso),
                )
            except sqlite3.IntegrityError as e:
                raise StorageConflictError(f"Project '{project.name}' already exists") from e

            # Also populate environments, suites, scenarios, datasets, contracts, gates
            for env in project.environments:
                conn.execute(
                    "INSERT INTO environments (project_name, name, data_json) VALUES (?, ?, ?)",
                    (project.name, env.name, env.model_dump_json()),
                )
            for suite in project.suites:
                conn.execute(
                    "INSERT INTO suites (project_name, name, data_json) VALUES (?, ?, ?)",
                    (project.name, suite.name, suite.model_dump_json()),
                )
                for sc in suite.scenarios:
                    conn.execute(
                        "INSERT INTO scenarios (project_name, suite_name, name, data_json) VALUES (?, ?, ?, ?)",
                        (project.name, suite.name, sc.name, sc.model_dump_json()),
                    )
            for ds in project.datasets:
                conn.execute(
                    "INSERT INTO datasets (project_name, name, version, data_json, created_at) VALUES (?, ?, ?, ?, ?)",
                    (project.name, ds.name, ds.version, ds.model_dump_json(), now_iso),
                )
            for c in project.contracts:
                if isinstance(c, Contract) and c.name:
                    conn.execute(
                        "INSERT INTO contracts (project_name, name, data_json) VALUES (?, ?, ?)",
                        (project.name, c.name, c.model_dump_json()),
                    )
            for g in project.quality_gates:
                conn.execute(
                    "INSERT INTO quality_gates (project_name, name, data_json) VALUES (?, ?, ?)",
                    (project.name, g.name, g.model_dump_json()),
                )

        return project

    def get_project(self, name: str) -> Optional[Project]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT data_json FROM projects WHERE name = ?", (name,)).fetchone()
            if not row:
                return None
            project = Project.model_validate_json(row["data_json"])
            # C.3: aggregate reads must reflect accepted sub-resource edits, too.
            project.environments = [Environment.model_validate_json(r[0]) for r in conn.execute(
                "SELECT data_json FROM environments WHERE project_name = ? ORDER BY rowid", (name,))]
            project.suites = [Suite.model_validate_json(r[0]) for r in conn.execute(
                "SELECT data_json FROM suites WHERE project_name = ? ORDER BY rowid", (name,))]
            project.quality_gates = [QualityGate.model_validate_json(r[0]) for r in conn.execute(
                "SELECT data_json FROM quality_gates WHERE project_name = ? ORDER BY rowid", (name,))]
            for index, contract in enumerate(project.contracts):
                if isinstance(contract, Contract) and contract.name:
                    current = conn.execute("SELECT data_json FROM contracts WHERE project_name = ? AND name = ?",
                                           (name, contract.name)).fetchone()
                    if current:
                        project.contracts[index] = Contract.model_validate_json(current[0])
            return project

    def list_projects(self) -> List[Project]:
        with self._get_connection() as conn:
            names = [row[0] for row in conn.execute("SELECT name FROM projects ORDER BY name")]
        return [self.get_project(name) for name in names]

    @synchronized
    def update_project(self, project: Project) -> Project:
        with self._get_connection() as conn:
            cur = conn.execute(
                "UPDATE projects SET data_json = ? WHERE name = ?",
                (project.model_dump_json(), project.name),
            )
            if cur.rowcount == 0:
                raise StorageNotFoundError(f"Project '{project.name}' not found")
            # Replace the live definition tree atomically. Runtime Evidence/Results
            # live in independent tables and must never be rewritten by this PUT.
            conn.execute("DELETE FROM suites WHERE project_name = ?", (project.name,))
            conn.execute("DELETE FROM environments WHERE project_name = ?", (project.name,))
            conn.executemany("INSERT INTO environments VALUES (?, ?, ?)",
                             [(project.name, env.name, env.model_dump_json()) for env in project.environments])
            for suite in project.suites:
                conn.execute("INSERT INTO suites VALUES (?, ?, ?)", (project.name, suite.name, suite.model_dump_json()))
                conn.executemany("INSERT INTO scenarios VALUES (?, ?, ?, ?)",
                                 [(project.name, suite.name, sc.name, sc.model_dump_json()) for sc in suite.scenarios])
            for contract in project.contracts:
                if isinstance(contract, Contract) and contract.name:
                    conn.execute("""INSERT INTO contracts VALUES (?, ?, ?)
                        ON CONFLICT(project_name, name) DO UPDATE SET data_json = excluded.data_json""",
                                 (project.name, contract.name, contract.model_dump_json()))
            conn.execute("DELETE FROM quality_gates WHERE project_name = ?", (project.name,))
            conn.executemany("INSERT INTO quality_gates VALUES (?, ?, ?)",
                             [(project.name, gate.name, gate.model_dump_json()) for gate in project.quality_gates])
            # Dataset versions are immutable registry entries, including versions no
            # longer included in the replacement's declarations (Appendix B B.3).
            for dataset in project.datasets:
                previous = conn.execute("SELECT data_json FROM datasets WHERE project_name = ? AND name = ? AND version = ?",
                                        (project.name, dataset.name, dataset.version)).fetchone()
                if previous and Dataset.model_validate_json(previous[0]) != dataset:
                    raise StorageConflictError(f"Dataset '{dataset.name}@{dataset.version}' is immutable")
                if not previous:
                    conn.execute("INSERT INTO datasets VALUES (?, ?, ?, ?, ?)",
                                 (project.name, dataset.name, dataset.version, dataset.model_dump_json(),
                                  datetime.now(timezone.utc).isoformat()))
        return project

    @synchronized
    def delete_project(self, project_name: str, retain_history: bool = False) -> None:
        """Delete a Project with referential integrity checks (Appendix C §C.8)."""
        with self._get_connection() as conn:
            # Check for history: baselines, reports, audit records
            b_count = conn.execute("SELECT count(*) as c FROM baselines WHERE project_name = ?", (project_name,)).fetchone()["c"]
            r_count = conn.execute("SELECT count(*) as c FROM reports WHERE project_name = ?", (project_name,)).fetchone()["c"]
            a_count = conn.execute("SELECT count(*) as c FROM audit_logs WHERE project_name = ?", (project_name,)).fetchone()["c"]

            has_history = (b_count > 0 or r_count > 0 or a_count > 0)
            if has_history and not retain_history:
                raise StorageConflictError(
                    f"DELETE /projects/{project_name} MUST NOT be permitted while the Project has Baselines, Reports, "
                    "or audit records unless retain_history is explicitly requested"
                )

            # Delete project
            cur = conn.execute("DELETE FROM projects WHERE name = ?", (project_name,))
            if cur.rowcount == 0:
                raise StorageNotFoundError(f"Project '{project_name}' not found")

    # ---------------- Environments ----------------

    @synchronized
    def create_environment(self, project_name: str, environment: Environment) -> Environment:
        with self._get_connection() as conn:
            p = conn.execute("SELECT name FROM projects WHERE name = ?", (project_name,)).fetchone()
            if not p:
                raise StorageNotFoundError(f"Project '{project_name}' not found")
            try:
                conn.execute(
                    "INSERT INTO environments (project_name, name, data_json) VALUES (?, ?, ?)",
                    (project_name, environment.name, environment.model_dump_json()),
                )
            except sqlite3.IntegrityError as e:
                raise StorageConflictError(f"Environment '{environment.name}' already exists in Project '{project_name}'") from e
        return environment

    def get_environment(self, project_name: str, env_name: str) -> Optional[Environment]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT data_json FROM environments WHERE project_name = ? AND name = ?",
                (project_name, env_name),
            ).fetchone()
            if not row:
                return None
            return Environment.model_validate_json(row["data_json"])

    def list_environments(self, project_name: str) -> List[Environment]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT data_json FROM environments WHERE project_name = ? ORDER BY name",
                (project_name,),
            )
            return [Environment.model_validate_json(row["data_json"]) for row in cursor]

    @synchronized
    def update_environment(self, project_name: str, environment: Environment) -> Environment:
        with self._get_connection() as conn:
            cur = conn.execute(
                "UPDATE environments SET data_json = ? WHERE project_name = ? AND name = ?",
                (environment.model_dump_json(), project_name, environment.name),
            )
            if cur.rowcount == 0:
                raise StorageNotFoundError(f"Environment '{environment.name}' not found in Project '{project_name}'")
        return environment

    @synchronized
    def delete_environment(self, project_name: str, env_name: str) -> None:
        # Appendix C §C.8: Check referential integrity with Baselines
        with self._get_connection() as conn:
            b_count = conn.execute(
                "SELECT count(*) as c FROM baselines WHERE project_name = ? AND environment_name = ?",
                (project_name, env_name),
            ).fetchone()["c"]
            if b_count > 0:
                raise StorageConflictError(
                    f"DELETE on Environment '{env_name}' MUST NOT be permitted because it is still referenced by an existing Baseline"
                )
            cur = conn.execute(
                "DELETE FROM environments WHERE project_name = ? AND name = ?",
                (project_name, env_name),
            )
            if cur.rowcount == 0:
                raise StorageNotFoundError(f"Environment '{env_name}' not found in Project '{project_name}'")

    # ---------------- Suites & Scenarios ----------------

    @synchronized
    def create_suite(self, project_name: str, suite: Suite) -> Suite:
        existing_gates = {g.name for g in self.list_quality_gates(project_name)}
        if any(g.name in existing_gates for g in suite.quality_gates):
            raise StorageConflictError("Quality Gate names must be unique across Project and Suites")
        with self._get_connection() as conn:
            p = conn.execute("SELECT name FROM projects WHERE name = ?", (project_name,)).fetchone()
            if not p:
                raise StorageNotFoundError(f"Project '{project_name}' not found")
            try:
                conn.execute(
                    "INSERT INTO suites (project_name, name, data_json) VALUES (?, ?, ?)",
                    (project_name, suite.name, suite.model_dump_json()),
                )
            except sqlite3.IntegrityError as e:
                raise StorageConflictError(f"Suite '{suite.name}' already exists in Project '{project_name}'") from e

            for sc in suite.scenarios:
                conn.execute(
                    "INSERT INTO scenarios (project_name, suite_name, name, data_json) VALUES (?, ?, ?, ?)",
                    (project_name, suite.name, sc.name, sc.model_dump_json()),
                )
        return suite

    def get_suite(self, project_name: str, suite_name: str) -> Optional[Suite]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT data_json FROM suites WHERE project_name = ? AND name = ?",
                (project_name, suite_name),
            ).fetchone()
            if not row:
                return None
            return Suite.model_validate_json(row["data_json"])

    def list_suites(self, project_name: str) -> List[Suite]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT data_json FROM suites WHERE project_name = ? ORDER BY name",
                (project_name,),
            )
            return [Suite.model_validate_json(row["data_json"]) for row in cursor]

    @synchronized
    def create_scenario(self, project_name: str, suite_name: str, scenario: Scenario) -> Scenario:
        with self._get_connection() as conn:
            s = conn.execute(
                "SELECT name, data_json FROM suites WHERE project_name = ? AND name = ?",
                (project_name, suite_name),
            ).fetchone()
            if not s:
                raise StorageNotFoundError(f"Suite '{suite_name}' not found in Project '{project_name}'")

            suite = Suite.model_validate_json(s["data_json"])
            if any(existing.name == scenario.name for existing in suite.scenarios):
                raise StorageConflictError(f"Scenario '{scenario.name}' already exists in Suite '{suite_name}'")

            try:
                conn.execute(
                    "INSERT INTO scenarios (project_name, suite_name, name, data_json) VALUES (?, ?, ?, ?)",
                    (project_name, suite_name, scenario.name, scenario.model_dump_json()),
                )
            except sqlite3.IntegrityError as e:
                raise StorageConflictError(f"Scenario '{scenario.name}' already exists in Suite '{suite_name}'") from e

            # Update suite scenarios in parent record
            suite.scenarios.append(scenario)
            conn.execute(
                "UPDATE suites SET data_json = ? WHERE project_name = ? AND name = ?",
                (suite.model_dump_json(), project_name, suite_name),
            )
        return scenario

    def get_scenario(self, project_name: str, suite_name: str, scenario_name: str) -> Optional[Scenario]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT data_json FROM scenarios WHERE project_name = ? AND suite_name = ? AND name = ?",
                (project_name, suite_name, scenario_name),
            ).fetchone()
            if not row:
                return None
            return Scenario.model_validate_json(row["data_json"])

    @synchronized
    def update_scenario(self, project_name: str, suite_name: str, scenario: Scenario) -> Scenario:
        with self._get_connection() as conn:
            s = conn.execute(
                "SELECT data_json FROM suites WHERE project_name = ? AND name = ?",
                (project_name, suite_name),
            ).fetchone()
            if not s:
                raise StorageNotFoundError(f"Suite '{suite_name}' not found in Project '{project_name}'")

            cur = conn.execute(
                "UPDATE scenarios SET data_json = ? WHERE project_name = ? AND suite_name = ? AND name = ?",
                (scenario.model_dump_json(), project_name, suite_name, scenario.name),
            )
            if cur.rowcount == 0:
                raise StorageNotFoundError(f"Scenario '{scenario.name}' not found in Suite '{suite_name}'")

            # Update suite
            suite = Suite.model_validate_json(s["data_json"])
            suite.scenarios = [scenario if sc.name == scenario.name else sc for sc in suite.scenarios]
            conn.execute(
                "UPDATE suites SET data_json = ? WHERE project_name = ? AND name = ?",
                (suite.model_dump_json(), project_name, suite_name),
            )
        return scenario

    @synchronized
    def delete_scenario(self, project_name: str, suite_name: str, scenario_name: str) -> None:
        with self._get_connection() as conn:
            s = conn.execute(
                "SELECT data_json FROM suites WHERE project_name = ? AND name = ?",
                (project_name, suite_name),
            ).fetchone()
            if not s:
                raise StorageNotFoundError(f"Suite '{suite_name}' not found in Project '{project_name}'")

            suite = Suite.model_validate_json(s["data_json"])
            if len(suite.scenarios) <= 1 and any(sc.name == scenario_name for sc in suite.scenarios):
                raise StorageConflictError("Cannot delete scenario: Suite MUST contain at least one Scenario")

            cur = conn.execute(
                "DELETE FROM scenarios WHERE project_name = ? AND suite_name = ? AND name = ?",
                (project_name, suite_name, scenario_name),
            )
            if cur.rowcount == 0:
                raise StorageNotFoundError(f"Scenario '{scenario_name}' not found in Suite '{suite_name}'")

            suite.scenarios = [sc for sc in suite.scenarios if sc.name != scenario_name]
            conn.execute(
                "UPDATE suites SET data_json = ? WHERE project_name = ? AND name = ?",
                (suite.model_dump_json(), project_name, suite_name),
            )

    # ---------------- Datasets (Versioned) ----------------

    def create_dataset(self, project_name: str, dataset: Dataset) -> Dataset:
        # Appendix B §B.3:
        # "Two configurations referencing the same Dataset name + version MUST resolve to identical rows."
        # Immutability: An existing name@version cannot be recreated or modified!
        with self._get_connection() as conn:
            p = conn.execute("SELECT name FROM projects WHERE name = ?", (project_name,)).fetchone()
            if not p:
                raise StorageNotFoundError(f"Project '{project_name}' not found")

            existing = conn.execute(
                "SELECT version FROM datasets WHERE project_name = ? AND name = ? AND version = ?",
                (project_name, dataset.name, dataset.version),
            ).fetchone()
            if existing:
                raise StorageConflictError(
                    f"Dataset '{dataset.name}@{dataset.version}' already exists and is immutable (Volume IV — Versioning)"
                )

            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO datasets (project_name, name, version, data_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (project_name, dataset.name, dataset.version, dataset.model_dump_json(), now_iso),
            )
        return dataset

    def get_dataset(self, project_name: str, dataset_name: str, version: Optional[str] = None) -> Optional[Dataset]:
        with self._get_connection() as conn:
            if version:
                row = conn.execute(
                    "SELECT data_json FROM datasets WHERE project_name = ? AND name = ? AND version = ?",
                    (project_name, dataset_name, version),
                ).fetchone()
            else:
                # Latest version by rowid
                row = conn.execute(
                    "SELECT data_json FROM datasets WHERE project_name = ? AND name = ? ORDER BY rowid DESC LIMIT 1",
                    (project_name, dataset_name),
                ).fetchone()
            if not row:
                return None
            return Dataset.model_validate_json(row["data_json"])

    def list_datasets(self, project_name: str) -> List[Dataset]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT data_json FROM datasets WHERE project_name = ? ORDER BY name, version",
                (project_name,),
            )
            return [Dataset.model_validate_json(row["data_json"]) for row in cursor]

    # ---------------- Reusable Contracts ----------------

    def create_contract(self, project_name: str, contract: Contract) -> Contract:
        if not contract.name:
            raise ValueError("Reusable Contract must have a 'name'")
        with self._get_connection() as conn:
            p = conn.execute("SELECT name FROM projects WHERE name = ?", (project_name,)).fetchone()
            if not p:
                raise StorageNotFoundError(f"Project '{project_name}' not found")
            try:
                conn.execute(
                    "INSERT INTO contracts (project_name, name, data_json) VALUES (?, ?, ?)",
                    (project_name, contract.name, contract.model_dump_json()),
                )
            except sqlite3.IntegrityError as e:
                raise StorageConflictError(f"Contract '{contract.name}' already exists in Project '{project_name}'") from e
        return contract

    def get_contract(self, project_name: str, contract_name: str) -> Optional[Contract]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT data_json FROM contracts WHERE project_name = ? AND name = ?",
                (project_name, contract_name),
            ).fetchone()
            if not row:
                return None
            return Contract.model_validate_json(row["data_json"])

    def list_contracts(self, project_name: str) -> List[Contract]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT data_json FROM contracts WHERE project_name = ? ORDER BY name",
                (project_name,),
            )
            return [Contract.model_validate_json(row["data_json"]) for row in cursor]

    @synchronized
    def update_contract(self, project_name: str, contract: Contract) -> Contract:
        if not contract.name:
            raise ValueError("Reusable Contract must have a 'name'")
        with self._get_connection() as conn:
            cur = conn.execute(
                "UPDATE contracts SET data_json = ? WHERE project_name = ? AND name = ?",
                (contract.model_dump_json(), project_name, contract.name),
            )
            if cur.rowcount == 0:
                raise StorageNotFoundError(f"Contract '{contract.name}' not found in Project '{project_name}'")
        return contract

    # ---------------- Quality Gates ----------------

    @synchronized
    def create_quality_gate(self, project_name: str, gate: QualityGate) -> QualityGate:
        if any(g.name == gate.name for g in self.list_quality_gates(project_name)):
            raise StorageConflictError("Quality Gate names must be unique across Project and Suites")
        with self._get_connection() as conn:
            p = conn.execute("SELECT name FROM projects WHERE name = ?", (project_name,)).fetchone()
            if not p:
                raise StorageNotFoundError(f"Project '{project_name}' not found")
            try:
                conn.execute(
                    "INSERT INTO quality_gates (project_name, name, data_json) VALUES (?, ?, ?)",
                    (project_name, gate.name, gate.model_dump_json()),
                )
            except sqlite3.IntegrityError as e:
                raise StorageConflictError(f"Quality Gate '{gate.name}' already exists in Project '{project_name}'") from e
        return gate

    def get_quality_gate(self, project_name: str, gate_name: str) -> Optional[QualityGate]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT data_json FROM quality_gates WHERE project_name = ? AND name = ?",
                (project_name, gate_name),
            ).fetchone()
            if not row:
                return next((g for suite in self.list_suites(project_name) for g in suite.quality_gates if g.name == gate_name), None)
            return QualityGate.model_validate_json(row["data_json"])

    def list_quality_gates(self, project_name: str) -> List[QualityGate]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT data_json FROM quality_gates WHERE project_name = ? ORDER BY name",
                (project_name,),
            )
            return [QualityGate.model_validate_json(row["data_json"]) for row in cursor] + [g for suite in self.list_suites(project_name) for g in suite.quality_gates]

    @synchronized
    def update_quality_gate(self, project_name: str, gate: QualityGate) -> QualityGate:
        with self._get_connection() as conn:
            cur = conn.execute(
                "UPDATE quality_gates SET data_json = ? WHERE project_name = ? AND name = ?",
                (gate.model_dump_json(), project_name, gate.name),
            )
            if cur.rowcount == 0:
                for suite in self.list_suites(project_name):
                    if any(g.name == gate.name for g in suite.quality_gates):
                        suite.quality_gates = [gate if g.name == gate.name else g for g in suite.quality_gates]
                        conn.execute("UPDATE suites SET data_json = ? WHERE project_name = ? AND name = ?",
                                     (suite.model_dump_json(), project_name, suite.name))
                        return gate
                raise StorageNotFoundError(f"Quality Gate '{gate.name}' not found in Project '{project_name}'")
        return gate

    # ---------------- Approvals & Audit ----------------

    def create_approval(self, approval: ApprovalRecord) -> ApprovalRecord:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO approvals (id, project_name, action, target_resource, requested_by,
                                      approved_by, status, created_at, external_review_reference, details_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval.id,
                    approval.project,
                    approval.action,
                    approval.target_resource,
                    approval.requested_by,
                    approval.approved_by,
                    approval.status.value,
                    approval.created_at.isoformat(),
                    approval.external_review_reference,
                    json.dumps(approval.details),
                ),
            )
        return approval

    def list_approvals(self, project_name: str) -> List[ApprovalRecord]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT id, project_name, action, target_resource, requested_by, approved_by,
                       status, created_at, external_review_reference, details_json
                FROM approvals WHERE project_name = ? ORDER BY created_at DESC
                """,
                (project_name,),
            )
            res = []
            for row in cursor:
                res.append(
                    ApprovalRecord(
                        id=row["id"],
                        project=row["project_name"],
                        action=row["action"],
                        target_resource=row["target_resource"],
                        requested_by=row["requested_by"],
                        approved_by=row["approved_by"],
                        status=ApprovalStatus(row["status"]),
                        created_at=datetime.fromisoformat(row["created_at"]),
                        external_review_reference=row["external_review_reference"],
                        details=json.loads(row["details_json"]),
                    )
                )
            return res

    def create_audit_entry(self, entry: AuditLogEntry) -> AuditLogEntry:
        from engine.audit import buffer_entry
        if buffer_entry(self, entry):
            return entry
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (id, project_name, action, principal_id, principal_kind, timestamp, details_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.project,
                    entry.action,
                    entry.principal_id,
                    entry.principal_kind.value,
                    entry.timestamp.isoformat(),
                    json.dumps(entry.details),
                ),
            )
        return entry

    def list_audit_logs(
        self,
        project_name: str,
        action: Optional[str] = None,
        principal_id: Optional[str] = None,
    ) -> List[AuditLogEntry]:
        with self._get_connection() as conn:
            query = "SELECT id, project_name, action, principal_id, principal_kind, timestamp, details_json FROM audit_logs WHERE project_name = ?"
            params: List[Any] = [project_name]
            if action:
                query += " AND action = ?"
                params.append(action)
            if principal_id:
                query += " AND principal_id = ?"
                params.append(principal_id)
            query += " ORDER BY timestamp DESC"

            cursor = conn.execute(query, params)
            res = []
            for row in cursor:
                res.append(
                    AuditLogEntry(
                        id=row["id"],
                        project=row["project_name"],
                        action=row["action"],
                        principal_id=row["principal_id"],
                        principal_kind=PrincipalKind(row["principal_kind"]),
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        details=json.loads(row["details_json"]),
                    )
                )
            return res
