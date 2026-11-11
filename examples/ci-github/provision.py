"""Provision an unprivileged Service Account for the local CI example."""

import os

from aqef_client import Client


with Client(os.environ["AQEF_URL"], os.environ["AQEF_TOKEN"]) as client:
    client.create_role({"name": "demo-ci", "permissions": ["read", "execute"]})
    client.create_principal({
        "id": "demo-ci", "kind": "service_account", "name": "Demo CI",
        "owner_person_id": "admin", "roles": ["demo-ci"], "token": os.environ["AQEF_CI_TOKEN"],
    })
