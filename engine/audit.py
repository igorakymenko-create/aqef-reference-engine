"""XII Principals/Audit: request-local audit of successful permission-checked actions."""
from contextvars import ContextVar
from dataclasses import dataclass, field
import uuid

from engine.models.principal import AuditLogEntry


@dataclass
class AuditRequest:
    request: object
    project: str | None = None
    permissions: dict = field(default_factory=dict)
    entries: list = field(default_factory=list)
    flushing: bool = False


active_audit = ContextVar("aqef_audit", default=None)


def bind_project(name):
    session = active_audit.get()
    if session is not None:
        session.project = name


def checked_permission(principal, permission, storage):
    session = active_audit.get()
    if session is not None:
        session.permissions[(principal.id, permission)] = (storage, principal)


def buffer_entry(storage, entry):
    session = active_audit.get()
    if session is None or session.flushing:
        return False
    session.entries.append((storage, entry))
    return True


def commit_audit(session):
    request = session.request
    project = session.project or request.path_params.get("project") or "__global__"
    target = request.url.path
    details = {"target": target, "method": request.method}
    if request.method == "DELETE":
        retain = request.query_params.get("retain_history", "false").lower() in ("true", "1", "on", "yes")
        if request.scope.get("route") and request.scope["route"].path == "/projects/{project}":
            details.update(retain_history=retain, deletion_kind="configuration_only_history_retained" if retain else "configuration_and_history")
        else:
            details.update(retain_history=True, deletion_kind="configuration_only_history_retained")
    entries = list(session.entries)
    recorded = {(entry.principal_id, entry.action) for _, entry in entries}
    for (principal_id, permission), (storage, principal) in session.permissions.items():
        if (principal_id, permission) not in recorded:
            entries.append((storage, AuditLogEntry(id=str(uuid.uuid4()), project=project,
                action=permission, principal_id=principal.id, principal_kind=principal.kind, details=details)))
    session.flushing = True
    for storage, entry in entries:
        # Preserve the more specific target in governed records, while retaining HTTP context.
        entry = entry.model_copy(update={"details": {**details, **entry.details}})
        storage.create_audit_entry(entry)
