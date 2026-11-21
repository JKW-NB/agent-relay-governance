"""Publish a verified approval POC scope using an explicit pointer revision."""
import argparse
import json
from urllib.error import HTTPError

from exercise_release_races import publish
from query_approval import ACTIVE, load_context


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate")
    parser.add_argument("--expect-scope", required=True)
    parser.add_argument("--expect-revision", required=True, type=int)
    args = parser.parse_args()
    if not args.candidate.startswith("viking://resources/") or args.expect_revision < 0:
        parser.error("provide a project resource scope and a nonnegative revision")
    try:
        outcome = publish(ACTIVE, args.expect_scope, args.expect_revision, args.candidate, load_context())
    except (HTTPError, ValueError, RuntimeError) as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}))
        return 1
    if outcome != "published":
        print(json.dumps({"status": outcome}))
        return 1
    print(json.dumps({"status": outcome, "scope": args.candidate, "revision": args.expect_revision + 1}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
