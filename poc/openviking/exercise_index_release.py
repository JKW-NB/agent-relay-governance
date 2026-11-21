"""Build and validate a synthetic OV index, then exercise one publisher."""
import hashlib
import json
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from evaluate import OV, request
from evaluate_natural_approvals import CASES
from query_approval import ACTIVE, RUNTIME, load_context, query, switch_index


def upload(record, scope, headers):
    boundary = uuid.uuid4().hex
    name = record["id"] + ".md"
    data = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
        f'Content-Type: text/markdown\r\n\r\n{record["text"]}\n\r\n--{boundary}--\r\n'
    ).encode()
    upload_headers = {**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"}
    req = Request(OV + "/resources/temp_upload", data, upload_headers)
    with urlopen(req, timeout=30) as response:
        payload = json.load(response)
    if payload["status"] != "ok":
        raise RuntimeError(payload.get("error"))
    request("/resources", headers, {
        "temp_file_id": payload["result"]["temp_file_id"], "parent": scope,
        "wait": True, "processing_mode": "vectors_only",
    })


def verify_manifest(scope, records, headers):
    manifest = []
    for key, record in records.items():
        target = f"{scope}/{key}"
        uri = f"{target}/{key}.md"
        text = request("/content/read?" + urlencode({"uri": uri}), headers).strip()
        if text != record["text"]:
            raise ValueError(f"Content differs: {key}")
        hits = request("/search/find", headers, {
            "query": text, "target_uri": target, "limit": 3,
        })["resources"]
        if not any(hit["uri"] == uri for hit in hits):
            raise ValueError(f"Record not searchable: {key}")
        manifest.append({"id": key, "uri": uri, "sha256": hashlib.sha256(text.encode()).hexdigest()})
    return manifest


def main():
    headers, records, directory = load_context()
    old = json.loads(ACTIVE.read_text(encoding="utf-8"))["scope"]
    release_id = uuid.uuid4().hex[:12]
    candidate = f"viking://resources/approval-release-{release_id}"
    request("/fs/mkdir", headers, {"uri": candidate})
    with tempfile.TemporaryDirectory(dir=RUNTIME, prefix="release-") as staging:
        active = Path(staging) / ACTIVE.name
        switch_index(active, old, headers, records, directory)
        old_bytes = active.read_bytes()
        start = threading.Barrier(5)
        published = threading.Event()
        rolled_back = threading.Event()
        reader_first = threading.Barrier(5)
        reader_new = threading.Barrier(5)

        def sample():
            scope = json.loads(active.read_text(encoding="utf-8"))["scope"]
            result = query(CASES[1][1], scope, headers, records, directory)
            assert scope in {old, candidate}, scope
            assert result["result"] == ("revoked", None, "APPROVAL-028"), result
            assert result["hit_source_uri"].startswith(scope + "/"), result
            return {"scope": scope, "status": result["status"], "source": result["hit_source_uri"]}

        def reader():
            start.wait(timeout=30)
            samples = [sample()]
            assert samples[0]["scope"] == old
            reader_first.wait(timeout=30)
            while not published.is_set():
                samples.append(sample())
            samples.append(sample())
            assert samples[-1]["scope"] == candidate
            reader_new.wait(timeout=30)
            while not rolled_back.is_set():
                samples.append(sample())
            samples.append(sample())
            assert samples[-1]["scope"] == old
            return samples

        with ThreadPoolExecutor(max_workers=4) as pool:
            readers = [pool.submit(reader) for _ in range(4)]
            try:
                start.wait(timeout=30)
                reader_first.wait(timeout=30)
                # Directory entries are present, but the revocation document is still absent.
                for key in directory.values():
                    upload(records[key], candidate, headers)
                try:
                    verify_manifest(candidate, records, headers)
                except HTTPError as error:
                    if error.code != 404:
                        raise
                    blocked = error.code
                else:
                    raise AssertionError("Incomplete candidate unexpectedly verified")
                assert active.read_bytes() == old_bytes
                for key, record in records.items():
                    if key not in directory.values():
                        upload(record, candidate, headers)
                manifest = verify_manifest(candidate, records, headers)
                switch_index(active, candidate, headers, records, directory)
                published.set()
                reader_new.wait(timeout=30)
                switch_index(active, old, headers, records, directory)
                assert active.read_bytes() == old_bytes
                rolled_back.set()
            finally:
                published.set()
                rolled_back.set()
                start.abort()
                reader_first.abort()
                if active.read_bytes() != old_bytes:
                    reader_new.abort()
        observations = [item for future in readers for item in future.result()]

    output = RUNTIME / f"approval-release-{release_id}.json"
    payload = {"old": old, "candidate": candidate, "incomplete_http_status": blocked,
               "manifest": manifest, "reader_count": 4, "observations": observations}
    with output.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2)
    print(f"Validated {len(manifest)} records and {len(observations)} concurrent reads")
    print(output)


if __name__ == "__main__":
    main()
