# Optional OpenViking evidence lookup

Use the standard ARG context-loading steps first. Run this helper only when project instructions explicitly opt in and the task needs historical evidence.

    python integrations/openviking/retrieve.py --project-root <project> --config <config.json> "<historical question>"

The config stays separate from CURRENT_STATE.yaml. It contains enabled, url, scope, and sources. The sources map uses the first directory after the configured Viking scope as its key. Each entry has a project-relative path and the SHA-256 of the original file bytes. An index must preserve this directory mapping. Trusted-mode deployments may also require account and user. Provide the service key via ARG_OV_API_KEY.

The helper accepts a loopback HTTP endpoint, requests at most five hits and returns only fragments found verbatim in hash-verified local files. Read the returned lines in context before relying on them. The helper treats approved local files as evidence and has no authority to change current state, decisions, approval or task status. Disabled, unavailable, invalid configuration and no verified evidence all leave the standard local flow available. If the task cannot proceed without evidence, follow the normal ARG blocker rules.

Start from config.example.json. Register the approved project-relative sources and their file digests before setting enabled to true. Keep the project instructions and the configuration path together so the next agent can opt in deliberately. The repository example is disabled.

Optional handoff preflight:

    python integrations/openviking/handoff.py --project-root <project> --config <config.json> --question "<historical question>"

Omit --question for a local-only check. The preflight lists the canonical task ID, current status, next action and required local files. It requires a checkpoint for PAUSED or HOLD. Other conditional loading rules are returned for the agent to evaluate. Missing required files prevent optional lookup. local_context_ready confirms file presence and state parsing; it does not mean the task is ready to advance or that historical evidence is sufficient.

### Optional operator-pinned handoff verification

    python integrations/openviking/verify_handoff.py --project-root <project> --policy <policy.json> --policy-sha256 <operator-pin>

The operator approves a policy before the handoff and supplies its SHA-256 independently of the project files. The policy contains project_root (the resolved absolute path with forward slashes) and tasks keyed by ARG task ID. Each task entry has a project-relative path, sha256, a JSON field path as an array of keys, and expected. The verifier compares the policy bytes to the supplied pin, reads the canonical task, then checks the registered report hash and value. The output is a read-only verification proposal.

The caller must protect both the pin and verifier invocation. A process that can replace the trusted pin, change the verifier, or bypass it is outside this control. OpenViking may help locate historical evidence; its output cannot replace the approved policy or report.

### Optional operator review of a proposal

    python integrations/openviking/review_handoff.py --project-root <project> --policy <policy.json> --policy-sha256 <operator-pin> --proposal <proposal.json>

A proposal contains exactly task_id, task_status and proposed_action. The operator provides the other arguments independently. The reviewer compares the proposal with canonical state and the pinned evidence decision. An accepted result is still a proposal for review and makes no state change. Reject a non-accepted status before any downstream action. This CLI does not install a host hook or create an OS permission boundary.

The local regression is poc/openviking/exercise_operator_review.py. It uses a temporary rehearsal directory and the recorded rollback evidence from the existing POC runtime.

For host callers, review_handoff.py exits 0 only for an accepted verification proposal, 3 for a matched HOLD proposal, and 1 for rejected or invalid input. Check the exit code and structured response. The host rehearsal uses a temporary marker on code 0 and replays three prior guided handoffs. It does not change ARG task state or install a host hook.

### Run the native ARG validator after operator review

    python integrations/openviking/dispatch_handoff.py --project-root <project> --policy <policy.json> --policy-sha256 <operator-pin> --proposal <proposal.json>

Only an accepted verification proposal starts the repository's native validator. The dispatcher rechecks the current state hash and reviewed inputs before and after validation. It emits a JSON receipt on stdout, including whether validation ran, its exit status and output when available, and the state hash on success. The caller can save the receipt for audit. The same 0, 3 and 1 exit codes distinguish success, HOLD and rejection. The checks detect observed changes and do not lock all project files or grant write authority.
