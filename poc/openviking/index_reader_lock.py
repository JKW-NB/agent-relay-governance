"""Shared Windows publication lock and query occupation for the isolated POC."""
import errno
import json
import msvcrt
import uuid
from contextlib import contextmanager

@contextmanager
def publication_lock(active):
    lock_path = active.with_suffix(".lock")
    with lock_path.open("a+b") as lock:
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def current_scope(active):
    return json.loads(active.read_text(encoding="utf-8"))["scope"]


@contextmanager
def lease(active):
    path = active.parent / f"reader-{uuid.uuid4().hex}.json"
    with publication_lock(active):
        scope = current_scope(active)
        stream = path.open("x+b")
        try:
            stream.write(json.dumps({"scope": scope}).encode())
            stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except BaseException:
            stream.close()
            path.unlink(missing_ok=True)
            raise
    try:
        yield scope
    finally:
        with publication_lock(active):
            stream.close()
            path.unlink(missing_ok=True)


def retention(active, candidate, rollback, managed, *, expected_revision=None):
    with publication_lock(active):
        pointer = json.loads(active.read_text(encoding="utf-8"))
        scope = pointer["scope"]
        revision = pointer.get("revision", 0)
        readers = []
        abandoned = []
        for path in active.parent.glob("reader-*.json"):
            with path.open("r+b") as stream:
                try:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as error:
                    if error.errno != errno.EACCES:
                        raise
                    # The locked byte is outside this read. The metadata is immutable.
                    stream.seek(1)
                    reader = json.loads(b"{" + stream.read())
                    readers.append(reader["scope"])
                else:
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                    abandoned.append(path.name)
        reasons = []
        if expected_revision is not None and revision != expected_revision:
            reasons.append('stale_snapshot')
        if candidate not in managed:
            reasons.append('unregistered')
        if candidate == scope:
            reasons.append("active")
        if candidate in rollback:
            reasons.append("rollback")
        if candidate in readers:
            reasons.append("in_use")
        return {"scope": candidate, "reasons": reasons, "eligible": not reasons,
                "active_readers": readers, "abandoned": abandoned, "revision": revision}
