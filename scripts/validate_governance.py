#!/usr/bin/env python3
"""validate_governance.py — Governance state integrity checker.

Validates a project's governance files (CURRENT_STATE.yaml, PROJECT_LOG.md,
CHECKPOINT.md, DECISIONS.md, SHA256 manifest) for the agent-relay-governance
protocol (V2).

Usage:
    python validate_governance.py [-p PROJECT_ROOT] [--check-hashes] [--max-stale-days N]

Exit code: 0 = PASS (warnings allowed), 1 = FAIL (errors present).

Pure Python standard library. YAML is parsed by a small built-in subset parser
covering exactly the constructs the governance templates use (indent nesting,
`key: value`, `- item` block lists, `[a, b]` flow lists, comments, quoted
scalars, empty-value keys that open a nested map or list). It is NOT a general
YAML parser — unsupported constructs raise ValueError with a line number.
"""

import argparse
import csv
import hashlib
import os
import re
import sys
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Mini YAML subset parser (governance-template dialect)
# ---------------------------------------------------------------------------

def _strip_comment(s):
    in_s = in_d = False
    for i, ch in enumerate(s):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == '#' and not in_s and not in_d:
            return s[:i]
    return s


def _parse_scalar(tok):
    tok = tok.strip()
    if tok in ('null', 'None', '~', ''):
        return None
    if tok in ('true', 'True'):
        return True
    if tok in ('false', 'False'):
        return False
    if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in ('"', "'"):
        return tok[1:-1]
    if re.fullmatch(r'-?\d+', tok):
        return int(tok)
    if re.fullmatch(r'-?\d+\.\d+', tok):
        return float(tok)
    return tok


def _parse_flow_list(s):
    s = s.strip()
    if not (s.startswith('[') and s.endswith(']')):
        return None
    inner = s[1:-1].strip()
    if not inner:
        return []
    items, buf, in_s, in_d = [], '', False, False
    for ch in inner:
        if ch == "'" and not in_d:
            in_s = not in_s
            buf += ch
        elif ch == '"' and not in_s:
            in_d = not in_d
            buf += ch
        elif ch == ',' and not in_s and not in_d:
            items.append(_parse_scalar(buf))
            buf = ''
        else:
            buf += ch
    items.append(_parse_scalar(buf))
    return items


def parse_yaml_subset(text):
    """Parse the governance YAML dialect into nested dicts/lists."""
    lines = [_strip_comment(l) for l in text.splitlines()]
    root = {}
    # stack of (indent, kind, container); kind in {'map','list'}
    stack = [(-1, 'map', root)]

    def find_list(item_indent):
        # list items are indented deeper than the key that opened the list
        for indent_, kind_, container in reversed(stack):
            if kind_ == 'list' and indent_ < item_indent:
                return container
        return None

    def clean_key(k):
        k = k.strip()
        if len(k) >= 2 and k[0] == k[-1] and k[0] in ('"', "'"):
            k = k[1:-1]
        return k

    i = 0
    while i < len(lines):
        raw = lines[i]
        if not raw.strip():
            i += 1
            continue
        indent = len(raw) - len(raw.lstrip(' '))
        lead = raw[:len(raw) - len(raw.lstrip())]
        if '\t' in lead:
            raise ValueError(f'line {i + 1}: tab indentation not supported')
        content = raw.strip()

        if content.startswith('- '):
            item_text = content[2:].strip()
            lst = find_list(indent)
            if lst is None:
                raise ValueError(f'line {i + 1}: list item without a list container at indent {indent}')
            if ':' in item_text and not item_text.startswith(('"', "'")):
                k, v = item_text.split(':', 1)
                item = {}
                lst.append(item)
                stack.append((indent, 'map', item))
                item[clean_key(k)] = _parse_flow_list(v.strip()) or _parse_scalar(v)
            else:
                fl = _parse_flow_list(item_text)
                lst.append(fl if fl is not None else _parse_scalar(item_text))
            i += 1
            continue

        if ':' not in content:
            raise ValueError(f'line {i + 1}: expected "key: value", got: {content[:40]}')
        k, v = content.split(':', 1)
        k = clean_key(k)
        v = v.strip()

        # pop deeper-or-equal containers (maps and lists alike) so `container`
        # is the map that should receive this key
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        if stack[-1][1] != 'map':
            raise ValueError(f'line {i + 1}: key {k!r} under a list container')

        container = stack[-1][2]
        fl = _parse_flow_list(v)
        if fl is not None:
            container[k] = fl
            stack.append((indent, 'map', container))
        elif v == '':
            # empty value opens a nested map or list; decide by the next
            # non-empty line's shape
            nxt = i + 1
            while nxt < len(lines) and not lines[nxt].strip():
                nxt += 1
            opens_list = nxt < len(lines) and lines[nxt].lstrip().startswith('- ')
            container[k] = [] if opens_list else {}
            stack.append((indent, 'list' if opens_list else 'map', container[k]))
        else:
            container[k] = _parse_scalar(v)
            stack.append((indent, 'map', container))
        i += 1

    return root


# ---------------------------------------------------------------------------
# File location helpers
# ---------------------------------------------------------------------------

HANDOFF_DIRS = ('_AI交接文件', '_ai_handoff', '')


def _find(root, names):
    for n in names:
        for d in HANDOFF_DIRS:
            p = os.path.join(root, d, n) if d else os.path.join(root, n)
            if os.path.isfile(p):
                return p
    return None


def _find_state(root):
    return _find(root, ['CURRENT_STATE.yaml'])


def _read(path):
    if not path or not os.path.isfile(path):
        return None
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------

STATUS_VOCAB = ('NOT_STARTED', 'READY', 'IN_PROGRESS', 'PAUSED', 'PASS', 'HOLD', 'LOCKED')


class Reporter:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, rule, msg, file=None, current=None, fix=None):
        self.errors.append((rule, msg, file, current, fix))

    def warning(self, rule, msg, file=None, current=None, fix=None):
        self.warnings.append((rule, msg, file, current, fix))

    def render(self):
        out = []
        for rule, msg, file, current, fix in self.errors:
            out.append(f'[FAIL] {rule}: {msg}')
            if file:
                out.append(f'  file   : {file}')
            if current is not None:
                out.append(f'  current: {current}')
            if fix:
                out.append(f'  fix    : {fix}')
        for rule, msg, file, current, fix in self.warnings:
            out.append(f'[WARN] {rule}: {msg}')
            if file:
                out.append(f'  file   : {file}')
            if current is not None:
                out.append(f'  current: {current}')
            if fix:
                out.append(f'  fix    : {fix}')
        return '\n'.join(out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description='Governance state integrity checker')
    ap.add_argument('-p', '--project-root', default='.')
    ap.add_argument('--check-hashes', action='store_true')
    ap.add_argument('--max-stale-days', type=int, default=30)
    args = ap.parse_args()

    root = os.path.abspath(args.project_root)
    rep = Reporter()

    state_path = _find_state(root)
    log_path = _find(root, ['PROJECT_LOG_工作日志.md', 'PROJECT_LOG.md'])
    checkpoint_path = _find(root, ['CHECKPOINT_项目断点.md', 'CHECKPOINT.md'])
    decisions_path = _find(root, ['DECISIONS.md'])
    manifest_path = _find(root, ['文件清单_SHA256.csv'])

    # ---- 1. schema completeness ----
    if state_path is None:
        rep.error('schema completeness', 'CURRENT_STATE.yaml not found',
                  file=root, fix='create it from assets/templates/CURRENT_STATE.template.yaml')
        state = {}
    else:
        text = _read(state_path)
        try:
            state = parse_yaml_subset(text)
        except ValueError as e:
            rep.error('schema completeness', f'YAML parse error: {e}',
                      file=state_path, fix='fix the YAML syntax')
            state = {}
        for field in ('project', 'last_updated'):
            if field not in state:
                rep.warning('schema completeness', f'missing top-level field: {field}',
                            file=state_path, fix=f'add "{field}: <value>"')
        if 'current' not in state:
            rep.error('schema completeness', 'missing "current" block',
                      file=state_path, fix='add current: {workstream, stage, task}')
        else:
            current = state['current']
            if not isinstance(current, dict):
                rep.error('schema completeness', '"current" must be a map',
                          file=state_path, fix='use the V2 template')
                current = {}
            for field in ('workstream', 'stage', 'task'):
                if field not in current:
                    rep.warning('schema completeness', f'missing "current.{field}" (V2 task contract)',
                                file=state_path,
                                fix='add current.task per assets/templates/CURRENT_STATE.template.yaml')
        if 'context' not in state:
            rep.warning('schema completeness', 'missing "context" block (V2 selective loading)',
                        file=state_path, fix='add context: {required, conditional, do_not_preload}')

    current = state.get('current') if isinstance(state.get('current'), dict) else {}
    task = current.get('task') if isinstance(current.get('task'), dict) else {}
    tstatus = task.get('status')

    # ---- 2. status vocabulary ----
    if tstatus is not None and tstatus not in STATUS_VOCAB:
        rep.error('state vocabulary', f'illegal status {tstatus!r}',
                  file=state_path, current=f'task.status={tstatus}',
                  fix=f'use one of {sorted(STATUS_VOCAB)}')
    elif tstatus is None:
        rep.warning('state vocabulary', 'no task.status found (V1 file?)',
                    file=state_path, fix='add current.task.status')

    # ---- 3. task id / stage consistency ----
    tid, stage = task.get('id'), current.get('stage')
    if tid and stage and not str(tid).startswith(f'T-{stage}-'):
        rep.warning('task id consistency', f'task.id {tid!r} does not match stage prefix T-{stage}-',
                    file=state_path, current=f'id={tid}, stage={stage}',
                    fix='use id format T-<stage>-<seq>')

    # ---- 4. referenced files exist ----
    def check_refs(refs, label, missing_is_error):
        for r in refs or []:
            r = str(r)
            if r.startswith(('http://', 'https://')):
                continue
            if not os.path.exists(os.path.join(root, r)):
                if missing_is_error:
                    rep.error('referenced files', f'{label} not found: {r}',
                              file=state_path, current=f'{label}={r}',
                              fix='create the file or fix the path')
                else:
                    rep.warning('referenced files', f'{label} not yet produced: {r}',
                                file=state_path, current=f'{label}={r}',
                                fix='produce the output before marking PASS')
    check_refs(task.get('inputs'), 'task.inputs', True)
    check_refs(task.get('outputs'), 'task.outputs', False)
    ctx = state.get('context') if isinstance(state.get('context'), dict) else {}
    check_refs(ctx.get('required'), 'context.required', True)
    for c in ctx.get('conditional') or []:
        if isinstance(c, dict):
            # conditional loads are only needed when their `when` holds — missing files are warnings
            check_refs(c.get('load'), 'context.conditional.load', False)

    # ---- 5. depends_on satisfied ----
    log_text = _read(log_path)
    for dep in (task.get('depends_on') or []):
        dep = str(dep)
        if log_text is None:
            rep.warning('dependency state', f'cannot verify {dep}: no PROJECT_LOG found',
                        file=state_path, fix='create PROJECT_LOG or remove depends_on')
        elif not re.search(r'\|\s*' + re.escape(dep) + r'\s*\|\s*END\b', log_text):
            rep.error('dependency state', f'depends_on {dep} has no END record in PROJECT_LOG',
                      file=state_path, current=f'depends_on={dep}',
                      fix=f'finish {dep} first or remove it from depends_on')

    # ---- 6. PASS requires verification evidence ----
    if tstatus == 'PASS':
        if log_text is None:
            rep.error('verification evidence', 'status=PASS but no PROJECT_LOG exists',
                      file=state_path, current='task.status=PASS',
                      fix='append an END entry with verification evidence to PROJECT_LOG')
        else:
            tid_pat = re.escape(str(task.get('id') or ''))
            tail = log_text[-3000:]
            has_own_end = bool(tid_pat) and bool(re.search(r'\|\s*' + tid_pat + r'\s*\|\s*END\b', tail))
            if not has_own_end:
                rep.error('verification evidence',
                          f'status=PASS but no recent END entry for {task.get("id")} in PROJECT_LOG',
                          file=log_path,
                          fix=f'append an END entry for {task.get("id")} with verification evidence')
            elif not re.search(r'验证|通过|verify|verified|evidence|N\s*=|p\s*=|hash|PASS', tail):
                rep.warning('verification evidence', 'END entry found but no explicit verification evidence',
                            file=log_path, fix='add evidence (numbers/hashes/commands) to the END entry')

    # ---- 7. PAUSED/HOLD require blocker or next action + checkpoint ----
    if tstatus in ('PAUSED', 'HOLD'):
        blocker, nexta = task.get('blocker'), task.get('exact_next_action')
        if not blocker and not nexta:
            rep.error('pause/hold consistency',
                      f'status={tstatus} but neither blocker nor exact_next_action set',
                      file=state_path, current=f'task.status={tstatus}',
                      fix='set task.blocker or task.exact_next_action; write CHECKPOINT')
        if checkpoint_path is None:
            rep.error('pause/hold consistency', f'status={tstatus} but no CHECKPOINT file found',
                      file=state_path, fix='write CHECKPOINT (resume package)')

    # ---- 8. blocker + PASS conflict ----
    blocker = task.get('blocker')
    if blocker and tstatus == 'PASS':
        rep.error('blocker consistency', 'task.blocker is set while status=PASS',
                  file=state_path, current=f'blocker={blocker}',
                  fix='clear blocker before PASS, or set status to HOLD')

    # ---- 9. CHECKPOINT vs CURRENT_STATE ----
    if checkpoint_path and tstatus:
        ck = _read(checkpoint_path)
        m = re.search(r'状态\s*[:：]\s*(\w+)', ck or '')
        if m and m.group(1) != tstatus:
            rep.warning('checkpoint consistency',
                        f'CHECKPOINT status={m.group(1)} differs from task.status={tstatus}',
                        file=checkpoint_path, current=f'{m.group(1)} vs {tstatus}',
                        fix='CURRENT_STATE wins; refresh CHECKPOINT or log a CORRECTION')

    # ---- 10. frozen decision not silently overridden ----
    dec_text = _read(decisions_path)
    if dec_text and log_text:
        frozen_ids = re.findall(r'##\s*(D-\d+)(?:(?!##).)*?status\s*[:：]\s*FROZEN', dec_text, re.S)
        for d in frozen_ids:
            if re.search(r'推翻|override|supersed|修改\s*' + re.escape(d), log_text):
                if not re.search(r'批准|人工|human', log_text[-2000:]):
                    rep.error('frozen decision protection',
                              f'PROJECT_LOG shows override of frozen decision {d} without human approval marker',
                              file=log_path, current=f'decision {d}',
                              fix='obtain human approval, log it explicitly, then update DECISIONS.md')

    # ---- 11. SHA256 manifest consistency (optional) ----
    if args.check_hashes:
        if manifest_path is None:
            rep.warning('sha256 manifest', '--check-hashes set but no manifest found', file=root)
        else:
            with open(manifest_path, 'r', encoding='utf-8-sig', errors='replace') as f:
                for row in csv.DictReader(f):
                    rel, want = row.get('relative_path'), row.get('sha256')
                    if not rel or not want:
                        continue
                    full = os.path.normpath(os.path.join(root, rel.replace('\\', '/')))
                    if not os.path.isfile(full):
                        rep.error('sha256 manifest', f'manifest row missing on disk: {rel}',
                                  file=manifest_path, fix='restore the file or remove the row')
                    else:
                        with open(full, 'rb') as fh:
                            got = hashlib.sha256(fh.read()).hexdigest().upper()
                        if got != want.upper():
                            rep.error('sha256 manifest', f'hash mismatch: {rel}',
                                      file=manifest_path, current=f'manifest={want}, disk={got}',
                                      fix='re-hash and update the manifest row')

    # ---- 12. staleness ----
    lu = state.get('last_updated') if state else None
    if lu:
        m = re.match(r'(\d{4})-(\d{2})-(\d{2})', str(lu))
        if m:
            d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if datetime.now() - d > timedelta(days=args.max_stale_days):
                rep.warning('staleness', f'last_updated {lu} older than {args.max_stale_days} days',
                            file=state_path, current=f'last_updated={lu}',
                            fix='refresh last_updated when state actually changes')

    # ---- render ----
    out = rep.render()
    if out:
        print(out)
        print()
    if rep.errors:
        print(f'GOVERNANCE_VALIDATION = FAIL '
              f'({len(rep.errors)} error(s), {len(rep.warnings)} warning(s))')
        return 1
    msg = 'GOVERNANCE_VALIDATION = PASS'
    if rep.warnings:
        msg += f' ({len(rep.warnings)} warning(s))'
    print(msg)
    return 0


if __name__ == '__main__':
    sys.exit(main())
