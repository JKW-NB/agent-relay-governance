"""Read-only, opt-in OpenViking evidence lookup for ARG handoffs."""
import argparse
import hashlib
import http.client
import json
import os
import re
from pathlib import Path
from urllib.parse import urlencode, urlsplit


def api(endpoint, headers, route, body=None):
    url = urlsplit(endpoint)
    if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "::1", "localhost"}
            or url.username or url.password or url.path not in ("", "/") or url.query or url.fragment):
        raise ValueError("Expected a local OpenViking HTTP endpoint")
    connection = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=3)
    try:
        connection.request("POST" if body is not None else "GET", "/api/v1" + route,
                           body=json.dumps(body).encode() if body is not None else None,
                           headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError(f"OpenViking HTTP {response.status}")
        payload = json.loads(response.read(2_000_001))
        if payload["status"] != "ok":
            raise RuntimeError("OpenViking did not return a successful result")
        return payload["result"]
    finally:
        connection.close()


def verify(root, entry, fragment):
    path = (root / entry["path"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry["sha256"]:
        return None
    source = data.decode("utf-8-sig").replace("\r\n", "\n")
    quote = fragment.replace("\r\n", "\n").strip()
    if not quote:
        return None
    start = source.find(quote)
    if start < 0:
        return None
    return {"path": path.relative_to(root).as_posix(), "sha256": entry["sha256"],
            "line": source.count("\n", 0, start) + 1, "quote": quote}


def lookup(root, config, question):
    if config.get("enabled") is not True:
        return {"status": "disabled", "evidence": []}
    scope = config["scope"]
    if not re.fullmatch(r"viking://resources/[A-Za-z0-9_.-]+", scope) or scope.endswith(("/.", "/..")):
        raise ValueError("Expected one dedicated resource scope")
    headers = {"Content-Type": "application/json"}
    if key := os.environ.get("ARG_OV_API_KEY"):
        headers["X-API-Key"] = key
    for name, header in (("account", "X-OpenViking-Account"), ("user", "X-OpenViking-User")):
        if name in config:
            headers[header] = config[name]
    try:
        hits = api(config["url"], headers, "/search/find",
                   {"query": question, "target_uri": scope, "limit": 5})["resources"]
        evidence = []
        for hit in hits:
            uri = hit["uri"]
            if not uri.startswith(scope + "/") or not uri.endswith(".md"):
                continue
            parts = uri.removeprefix(scope + "/").split("/")
            if len(parts) < 2 or any(part in {"", ".", ".."} for part in parts):
                continue
            entry = config["sources"].get(parts[0])
            if entry is None:
                continue
            fragment = api(config["url"], headers, "/content/read?" + urlencode({"uri": uri}))
            original = verify(root, entry, fragment)
            if original:
                evidence.append({"uri": uri, **original})
        return {"status": "verified_evidence" if evidence else "no_verified_evidence", "evidence": evidence}
    except (OSError, http.client.HTTPException, RuntimeError):
        return {"status": "unavailable_use_local", "evidence": []}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("question")
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8-sig")) if args.config else {}
        result = lookup(args.project_root.resolve(), config, args.question)
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
        result = {"status": "invalid_config_use_local", "error": type(error).__name__, "evidence": []}
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
