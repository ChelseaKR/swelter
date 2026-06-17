"""Thin Lambda entry point for swelter's READ-ONLY API (OPTIONAL serverless mode).

This is a stub on purpose. The job of the Lambda is to answer swelter's GET routes
(/v1.1/... SensorThings, /api/surface.json, /export.csv, /export.json, /health) from a read-only
snapshot of the store, and otherwise scale to zero. A real deployment wires this to the swelter
package's request handling; how you package that — bundle the `swelter` wheel and a copy of the
store folder into the function, or mount them from a layer — is left to the deployer and documented
in ../README.md, so this minimal stack stays readable and dependency-free.

The contract below is the Lambda function-URL event/response shape, so the surrounding stack is
complete and deployable as-is for a smoke test before you bundle swelter in.
"""

from __future__ import annotations

import json
from typing import Any

# The GET-only public surface, matching swelter.server's routes. There is no write path here, by
# construction: the function never mutates anything, it only reads a published snapshot.
READ_ONLY = True


def handler(event: dict[str, Any], _context: object) -> dict[str, Any]:
    """Answer a Lambda function-URL request.

    Replace the body of the dispatch with a call into the swelter package once it is bundled. Until
    then this returns a health response so the stack can be deployed and exercised end to end.
    """
    method = (
        event.get("requestContext", {}).get("http", {}).get("method", "GET")
    )
    path = event.get("rawPath", "/")

    # Read-only by construction: anything other than GET is refused, the same as the stdlib server.
    if method != "GET":
        return _response(405, {"error": "swelter's public API is read-only"})

    if path in ("/", "/health"):
        return _response(200, {"status": "ok", "readOnly": READ_ONLY})

    # TODO(deployer): dispatch path to the swelter API handler against the snapshot store, e.g.
    #   from swelter import server, store, config
    #   ... build a ServerContext over a read-only snapshot and route `path` ...
    return _response(
        501,
        {
            "error": "not wired up",
            "hint": "bundle the swelter package + a read-only store snapshot; see infra/cdk/README.md",
        },
    )


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "content-type": "application/json",
            # Open data: open CORS, matching the stdlib server.
            "access-control-allow-origin": "*",
            "cache-control": "public, max-age=60",
        },
        "body": json.dumps(body),
    }
