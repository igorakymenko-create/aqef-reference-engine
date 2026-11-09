# AQEF Python SDK

Install the separate distribution with `python -m pip install ./client` from the
repository root. The import package is `aqef_client`. The same installation
provides the [CLI](CLI.md).

Construct a `Client` with the engine base URL and the caller's bearer token.
Read credentials from the environment or a protected file. Use the context
manager to close the HTTP connection pool. The default HTTP timeout is 60
seconds. Pass `timeout=` to use a different finite value.

```python
import os
from pathlib import Path

import yaml
from aqef_client import APIError, Client, TransportError

definition = yaml.safe_load(Path("project.yaml").read_text(encoding="utf-8"))
try:
    with Client(os.environ["AQEF_URL"], os.environ["AQEF_TOKEN"]) as api:
        project = api.create_project(definition).json()["name"]
        batch = api.trigger_execution(
            project, {"suite": "smoke", "environment": "test"},
        ).json()
        for execution in batch["executions"]:
            results = api.list_results(project, execution["id"]).json()
            print(results)
        evaluation = api.check_gates(
            project, {"execution_batch_id": batch["execution_batch_id"]},
        ).json()
        print(evaluation["gates"])
except APIError as error:
    print(error.status_code)
    # error.body contains the exact API bytes. Treat them as API data.
    raise
except TransportError:
    raise
```

Use a configuration that declares the named Suite and Environment and configure
the engine's subject provider before running this example.

All operation methods return the original `httpx.Response`. Call `.json()` to
decode JSON or use `.content` to obtain response bytes. An HTTP error raises
`APIError` with `.status_code`, `.body` (bytes), and `.response`. Its exception
message contains only the status. Transport failures raise `TransportError`.
For HTTP 204, read the status or empty body directly.

For an API-relative call, use
`api.request("GET", "/projects", params={"offset": 0, "limit": 20})`.
The method accepts optional `params`, `headers`, and a JSON `body`. Omit the
`body` argument for no body. Explicit `body=None` sends JSON null. Named methods
provide the published path/query parameters and accept an unmodified body value
where the API defines a body. Pagination is explicit, using the API's offsets
and limits.

Pass `x_approved_by=` and `x_external_review_ref=` on operations that expose
those headers. The server decides whether they are required and whether the
Principal may act. The [operation table](CLI.md) lists the full SDK surface and
each corresponding API route. Method docstrings repeat the verb and path.

Maintainers can regenerate the named methods, CLI inventory and command table
from the published OpenAPI with `python client/tools/generate_operations.py`.
To run the suite against an installed console script, install the client first
or set `AQEF_TEST_CLI` to the path of an installed `aqef` executable. The checks
also support running the entry point as a Python module in source checkouts.
