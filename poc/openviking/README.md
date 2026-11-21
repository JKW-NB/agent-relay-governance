# ARG × OpenViking POC

OpenViking indexes disposable copies of synthetic historical evidence. In ARG V2, CURRENT_STATE owns current state, CHECKPOINT owns the recovery package, PROJECT_LOG owns events, DECISIONS owns decisions and LESSONS owns procedures. Resolve findings against the owning source. This experiment uses resource search via the official HTTP API.

1. Start a dedicated OpenViking instance on loopback with an embedding model and a dedicated data directory within the project. See https://docs.openviking.ai/en/configuration/01-server and https://docs.openviking.ai/en/guides/07-operation-telemetry. Set ARG_POC_OV_API_KEY in the process environment if required.
2. Import only fixtures using the official resource import flow with indexing completion enabled. Use the returned resource root as target_uri in config.json. Run python poc/openviking/find.py from the repo root. Save the response under the POC directory.
3. Audit the top five hits. Record rank, URI, score and evidence ID. Read each cited URI through OpenViking and compare its evidence text to the corresponding local file. Record missing, mismatched and unverifiable sources separately.

## Paired evaluation

Give G0 and G1 the same query in config.json, the same fixtures, model, instructions, time limit and citation format, with fresh sessions. G0 can inspect the original files using native file tools. G1 has those tools plus the scoped OpenViking results. Ask both to cite the decision and the incident, then repeat with a paraphrase that omits the terms SHA-256 and file size. Use the same paraphrase in both groups. Include a negative control asking who approved the change, which is absent from the corpus.

Expected evidence is DEC-009 for the selection and LOG-014 for the same-length edit. LOG-021 is a distractor. Record per-task answer correctness, verified citations out of submitted citations, elapsed time, and for G1 recall@5 against the two expected sources. Report per-task results and errors before comparing groups. Treat this corpus as a smoke test and expand it before estimating any improvement.

## Local baseline

Windows. Git 2.53.0.windows.2, Python 3.14.7, uv 0.9.10 and Docker CLI 29.3.1 detected. The active Python did not report OpenViking installed. The initial TCP probe on localhost:1933 failed.
