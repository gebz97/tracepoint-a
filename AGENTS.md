# AGENTS.md — tracepoint-a (tpa)

Guidance for AI agents working in this repository. Read this before making
changes — several patterns here exist because of past bugs, and reverting to
the "obvious" approach reintroduces them.

## What this project is

`tpa` is an agentless infrastructure inventory CLI. It SSHes into Linux hosts
(RHEL/systemd-family and Debian/dpkg-family), collects facts (disks, NICs,
mounts, users/groups, systemd daemons, packages, host info), and stores them
in PostgreSQL. It optionally pulls errata counts from a Foreman/Satellite
instance. Resources no longer present on a host are marked `is_stale`, never
deleted.

Non-goals (don't silently expand scope into these without being asked):
Windows hosts, non-systemd init systems, macOS, agent-based collection.

## Project layout

```
tpa.py                    - CLI entry point, registers all click commands
lib/config.py              - loads config.yaml (or $TPA_CONFIG), one module-level cache
lib/db.py                  - engine/sessionmaker singletons + session_scope() contextmanager
lib/models.py               - SQLAlchemy 2.0 typed models
lib/ssh.py                  - SSH connection handling (host key policy, retries, credentials)
lib/sync_runner.py          - shared parallel sync orchestration (run_sync, run_multi_sync)
lib/progress.py              - stdout progress line, single writer from main thread
lib/collectors/              - per-resource SSH collectors (pure functions: client -> data)
lib/commands/                - click command definitions (migrate, synchosts, sync, reports)
alembic/versions/            - schema migrations, chained, never hand-edited after merge
```

## Core patterns — follow these, don't reinvent

### 1. Threading model: primitives only cross thread boundaries

`sync_runner.py`'s worker threads (`ThreadPoolExecutor`) must only touch
plain Python values (host id/name tuples, dicts, exceptions) — never live
SQLAlchemy ORM objects and never a live `Session`. Sessions are opened via
`session_scope()` in the **main thread only**, before threads start (to read
host list) and after they finish (to write results back). This was a real
bug previously (`run_foreman_sync` passed live `Host` objects into worker
threads) and was deliberately fixed. Any new code that touches the DB from
inside a `_work()`-style function is a regression — don't do it.

### 2. `session_scope()` is the only way to touch the DB

```python
from lib.db import session_scope
with session_scope() as session:
    ...  # commits on success, rolls back on exception, always closes
```

Never instantiate a `Session` directly outside this contextmanager.

### 3. Write-back is one bulk query per resource, not N

`sync_runner._write_back()` loads all existing rows for the touched hosts
with a single `.filter(model_cls.host_id.in_(host_ids))` query, then upserts
in Python by `natural_key_fields`. Don't reintroduce a per-host query in a
loop — that was a real N+1 bug that was fixed.

### 4. Collectors are pure functions: `(SSHClient) -> list[dict] | dict`

Everything in `lib/collectors/` takes a connected `paramiko.SSHClient` and
returns plain data — no DB access, no config access, no logging side effects
beyond what's necessary. `daemons.py`, `disks.py`, `net.py` parse structured
command output (`systemctl show`, `lsblk -J`, `ip -j addr`) in preference to
scraping free-text where the remote tool supports a machine-readable mode —
follow that precedent for new collectors rather than regex-scraping text
output if a `-j`/`--format=json` equivalent exists.

If a collector needs more than one read of the same remote state (e.g.
`users.py` needs `/etc/group` for both groups and supplementary
memberships), factor it so **one SSH round trip** produces everything needed
— see `users_c.collect_users_and_groups()` and `run_multi_sync()`. Don't add
a second `client.exec_command()` round trip for data already available from
a prior command's output in the same sync.

### 5. Natural keys drive upsert identity, not the PK

Every syncable model declares its dedupe/upsert identity via
`natural_key_fields` passed to `run_sync`/`run_multi_sync` (e.g.
`("host_id", "disk_path")` for disks). This must match the model's actual
`UniqueConstraint` in `lib/models.py` and the corresponding Alembic
migration. If you add a resource type, all three must agree.

### 6. `StaleMixin` and the stale pattern

Per-host child resources (`Disk`, `Nic`, `Mount`, `Group`, `User`, `Daemon`,
`Package`) inherit `StaleMixin` (`first_seen`, `last_seen`, `is_stale`).
Resources no longer observed on a sync are marked `is_stale = True`, never
deleted — this is intentional, preserves history, and downstream reporting
relies on it. Don't add a hard-delete path for these tables. `Host` uses its
own `stale` boolean field for the same purpose (inconsistent naming with
`is_stale` on children — known, not currently worth a migration to unify
unless you're asked to).

### 7. SSH connection policy (`lib/ssh.py`)

`ssh.strict_host_key_checking` in config controls trust:

- `true` — reject unknown/changed keys, actionable error with fingerprint
- `new` — TOFU-accept unknown keys (should persist to `known_hosts_path` via
  `save_host_keys()` after a successful connect on first contact — verify
  this is actually happening if you touch this file, it's a known gap)
- `false` — accept anything, insecure, dev-only

Retries (`ssh.retries`) do not apply to `AuthenticationException` or
`BadHostKeyException` — those are deterministic, not transient. Preserve
that distinction (`_NO_RETRY` tuple) if you touch the retry loop.

Credentials come from `credentials.<name>` in config, selected by
`ssh.credential` (defaults to `default`). There is currently no per-host or
per-group credential routing — one credential per sync run for the whole
fleet. Don't assume otherwise; don't silently add per-host credential
support without it being an explicit task.

### 8. Progress and logging are single-threaded by design

`progress()`/`progress_end()` write to stdout from the main thread only, as
futures complete via `as_completed()`. Per-host errors are collected as
`(host_id, kind, err)` tuples during the threaded phase and logged via
`_log_errors()` **after** the pool closes — not from inside worker threads.
This avoids interleaved/garbled output. Keep this ordering if you add new
per-host telemetry (e.g. audit/failure persistence): collect in the loop,
persist/log after the pool closes, in the main thread.

### 9. Migrations

Alembic migrations chain off the current head — check
`alembic/versions/` for the latest `down_revision` before creating a new
one. Never edit a migration that's already been merged; add a new one. New
tables are additive; don't alter existing table shapes without an explicit
task to do so, since existing sync/report code depends on current columns.

### 10. Reports (`lib/commands/reports.py`)

New reportable tables get added to the `REPORTS` dict (model class + field
list) — this alone is what wires up a `get <name> --csv/--stdout` CSV
subcommand generically. Don't hand-roll a new command for a new report;
extend `REPORTS`.

## Known gaps (don't "fix" silently — flag or ask if a task touches these)

- `ssh.strict_host_key_checking: new` may not actually persist newly-seen
  host keys (`save_host_keys()` call needs verification) — first contact may
  behave like `new` forever rather than pinning after first success.
- Commands exit 0 even on partial per-host failure. No task should quietly
  change this without being asked, since it may be relied upon by existing
  cron/orchestration.
- `credentials.<name>` only supports one credential per sync run; a `vault`
  example entry in `example.config.yaml` is illustrative, not functional —
  nothing resolves credentials per-host/per-group yet.
- `satellite`/Foreman integration assumes RHEL-family + Satellite; not
  something to assume is desired for a Debian-focused change.
- `Host.stale` vs children's `is_stale` naming inconsistency is known and
  not currently worth a migration on its own.

## Style conventions observed in this codebase

- SQLAlchemy 2.0 typed `Mapped[...]` / `mapped_column(...)` style throughout
  `lib/models.py` — match this, don't drop to legacy `Column(...)` style.
- Click for all CLI commands, one `@click.command()` per file/function in
  `lib/commands/`, registered explicitly in `tpa.py`.
- Functions returning "did this fail" info use `None` as the failure sentinel
  in tuples (e.g. `(host_id, rows_or_None, kind, err)`), checked by the
  caller — follow this rather than raising through the thread pool boundary,
  since exceptions don't cross `ThreadPoolExecutor.submit()` cleanly without
  being wrapped in the `Future`.
- Config access always goes through `lib/config.py`'s getter functions
  (`get_credential`, `get_ssh_settings`, `get_database_url`,
  `get_satellite_settings`) — never read `config.yaml` directly elsewhere.
- `# pyrefly: ignore [...]` comments mark known type-checker gaps for
  untyped third-party imports (`paramiko`, `yaml`, `powerdrill`) — keep these
  on new imports of the same libraries rather than re-triggering the same
  warnings.

## Before submitting a change

- If you touched `sync_runner.py`, `sync.py`, or `synchosts.py`: re-check
  that no ORM object or `Session` crosses a `ThreadPoolExecutor` boundary.
- If you added a resource/model: confirm `natural_key_fields`, the
  `UniqueConstraint` in `models.py`, and the Alembic migration all agree.
- If you added a report: confirm it's wired via `REPORTS`, not a bespoke
  command.
- If you touched `ssh.py`: confirm retry/no-retry exception classification
  is preserved and host-key modes (`true`/`new`/`false`) still behave as
  documented in the README.

## Testing

Test objectives here are scoped to what actually breaks in this codebase —
parsers fed real-world messy output, merge/upsert logic, and concurrency
invariants. Do not write tests that just re-assert a mock was called, or that
patch out the exact logic under test and check nothing. If a test can pass
while the implementation is deleted, it's theater — delete it or rewrite it.

### Priority order (highest-value first)

1. **Pure-function collectors and parsers** — no SSH, no DB, no threading.
   These are the cheapest to test well and the most likely to silently break
   from a remote OS/tool version change nobody controls. This is where most
   test effort should go.
2. **Upsert/merge/conflict logic** — `_write_back`'s natural-key upsert,
   `foreman.match_hosts`, `mounts.collect`'s fstab/live/df merge. Wrong here
   means silently wrong data in the DB, not a crash — the worst failure mode.
3. **Concurrency invariants** — no live ORM object or `Session` crosses a
   `ThreadPoolExecutor` boundary; errors collected during the threaded phase
   are the ones that end up logged/persisted, not lost.
4. **CLI/command-level integration** — thinnest layer, test last, only for
   wiring (does `syncusers` actually call `run_multi_sync` with the right
   resources), not for re-testing logic already covered at level 1–2.

Do not write tests for SQLAlchemy itself, Paramiko itself, or Click itself.
Test _your_ logic built on top of them.

### 1. Collector/parser tests — real fixture data, not synthetic happy paths

Every collector test must use fixture strings that look like actual remote
command output, including the messy edges — not a clean synthetic example
that happens to match the parser's expectations.

**`daemons.py` — `_parse_usec`:**

- `"0"` → `None`, `"infinity"` → `None` (explicit sentinels, not "0 seconds")
- `"1min 30s"` → `90`, mixed-unit compound string
- `"500ms"` → `0` (sub-second durations truncate to 0, not None — confirm
  this is actually the intended behavior, since `int(total) or None` turns a
  computed `0` into `None` too — **this is a real ambiguity bug to write a
  test that exposes**: `"500ms"` produces `total=0.5`, `int(0.5)=0`,
  `0 or None → None`. Write the test, see it return `None` for a
  half-second restart delay, and decide if that's actually correct before
  moving on — don't just document the current behavior as if it were
  designed.)
- Garbage input `"banana"` → `None`, not an exception
- Empty string → `None`

**`daemons.py` — `_parse_exec_prop`:**

- Real systemd output format: `"{ path=/usr/bin/foo ; argv[]=/usr/bin/foo --flag ; ignore_errors=no ; start_time=... }"` → extracts just the argv command
- Value with no `argv[]=` marker → returned as-is, not `None`
- Empty string → `None`

**`daemons.py` — `collect()` chunking:**

- Feed a fake `SSHClient` (see fixtures below) with 450 fake unit names →
  assert `exec_command` is called exactly 3 times (`UNIT_CHUNK=200`), not
  once, and that the parsed results still union correctly across chunks
  with a daemon record's key=value block spanning a chunk boundary
  correctly parsed (blank-line-delimited records must not merge across
  the chunk seam)

**`disks.py` — `collect()`:**

- Real `lsblk -J` output with nested `children` (partition inside disk),
  confirm `walk()` recurses and both parent disk and child partition are
  captured with independent `boot_disk` flags
- Device with `size` as a string vs int (lsblk JSON output has been known
  to vary) → doesn't crash, falls back to `size_gb=0`
- Malformed/truncated JSON (simulate a command that got cut off mid-output,
  a real failure mode over flaky SSH) → returns `[]`, doesn't raise
- `mountpoint` is `null` in JSON vs missing key entirely → both handled
  identically

**`mounts.py` — `collect()`, the merge logic specifically:**
This is the single highest-value test target in the collectors — it merges
three independent command outputs (fstab, live `mount`, `df`) and the merge
semantics matter:

- A mountpoint present in fstab but NOT currently mounted → `status:
"fstab_only"`, `in_fstab: True`, no size/used stats
- A mountpoint currently mounted but NOT in fstab (e.g. manual `mount`) →
  `status: "mounted"`, `in_fstab: False`
- A mountpoint in both → live entry wins for `source`/`fstype`/`opts`
  (confirm this precedence explicitly — it's implicit in `entry =
live[mp] if in_live else fstab.get(mp, {})` and easy to invert by
  accident in a refactor)
- `df` output with a value that fails `int()`/`float()` parsing (e.g. `df`
  printed `-` for an inaccessible mount) → that mountpoint's stats are
  skipped, doesn't crash the whole collector
- A mountpoint under `/proc`, `/sys` with an fstype NOT in
  `IGNORED_FSTYPES` (prefix-based exclusion vs fstype-based exclusion are
  two independent filters — test each triggers independently, and test a
  case where only one of the two would exclude it)

**`net.py` — `collect()`:**

- Interface with only an IPv6 address, no IPv4 → `ipv4: None` correctly,
  not a crash on missing key
- `lo` interface present in raw JSON → excluded from output
- Interface with `addr_info` containing more than one `inet` entry
  (secondary IPs) → confirm only the first is kept (`not ipv4` guard) and
  this is the intended "primary IP" semantic, not an accidental drop of data

**`hostinfo.py` — `_parse_os_release` / `_parse_os_version` / Debian fallback:**

- Standard `/etc/os-release` with quoted values → quotes stripped
- Line with `=` inside a quoted value (e.g. `PRETTY_NAME="Foo (v=2)"`) →
  `partition("=")` only splits on the first `=`, confirm the value isn't
  truncated
- `VERSION_ID="13.1"` → major `"13"`, minor `"1"`
- Debian case: `ID=debian`, `VERSION_ID` present but no minor component →
  confirm the `/etc/debian_version` fallback (`"13.1"` or `"13/trixie"`)
  correctly fills `os_minor` and doesn't override an already-present value
- `/etc/debian_version` in pre-release form `"trixie/sid"` → doesn't crash,
  `os_major`/`os_minor` may legitimately be `None`

**`pkg.py` — `_probe_package_manager` and both collectors:**

- `command -v rpm dpkg-query` returns both found → `rpm` wins (test the
  precedence order in `("rpm", "dpkg-query")` explicitly, don't assume)
- Neither found → raises `RuntimeError`, and confirm this propagates as a
  `"collect"`-kind failure through `sync_runner`, not an uncaught crash
- `dpkg-query` output with a multi-line `Description` field → only the
  first line is kept as `summary`
- RPM `license` field literal `"(none)"` → normalized to `None`

**`users.py` — `_parse_group_lines` / `_build_users`:**

- `/etc/group` line with empty member list (`group:x:100:`) → group parsed,
  no entries added to `user_supgroups`
- User in `/etc/passwd` with a non-numeric UID field (corrupted line) →
  skipped, not crashed
- User whose primary GID has no matching group in `/etc/group` →
  `pgroup` falls back to the raw gid string, not `None` or a crash
- `getent group sudo wheel` returns nothing (neither group exists on this
  distro) → `sudo_users` is empty set, `has_sudo` correctly `False` for
  everyone, not an exception

**`identity.py` — UUID validation:**

- Valid UUID with mixed case → normalized to lowercase and accepted
- Command output with trailing whitespace/newline noise → still matches
- Non-UUID garbage (e.g. shell error text leaked into stdout) → returns
  `None`, and confirm the caller (`synchosts.py`) actually skips
  registering the host in this case (this is a cross-module test, and
  correctness-critical: registering a host with no identity string as the
  `machine_id` would break the whole merge-on-rename feature)

### 2. Upsert / merge / conflict-resolution tests

**`sync_runner._write_back`:**

- Existing row for a host, new sync returns a row with the same natural
  key but changed data → existing row's fields updated in place, `is_stale`
  reset to `False`, no duplicate row created
- Existing row's natural key NOT present in this sync's results →
  `is_stale` set `True`, row NOT deleted
- Two different hosts each get a `None` natural-key field (edge case: a
  disk with no `disk_path`) — confirm they don't collide as the same
  "row" across hosts (natural key includes `host_id`, verify this isn't
  accidentally omitted for any resource type registered in `sync.py`)
- A resource's `natural_key_fields` tuple doesn't match its model's
  `UniqueConstraint` — this should be caught by a **schema-consistency
  test**, not discovered at runtime: iterate `sync.py`'s registered
  `(name, model_cls, natural_key_fields)` tuples and assert each matches
  the model's actual `__table_args__` unique constraint columns.

**`foreman.match_hosts`:**
This function's docstring specifies exact precedence and conflict rules —
test every rule it claims, not just the common case:

- DB host matches by name only → matched, no conflict
- DB host's name matches one satellite host, but its IP matches a
  _different_ satellite host → both appear in `hits`, conflict recorded,
  first-priority (name) match wins
- Two DB hosts both resolve to the same satellite host id → first
  claimant wins, second left as `_CONFLICT`, and conflict message names
  both hosts
- Two satellite hosts registered under the same name (satellite-side dup)
  → `by_name` indexing records a conflict and does NOT let the second one
  silently overwrite the first
- DB host absent from satellite entirely → `plan[host] is None`, not a
  `KeyError` or missing dict entry
- Empty `sat_hosts` list → every DB host maps to `None`, zero conflicts,
  no exception

**Regression test for the already-fixed N+1 bug:** assert `_write_back`
issues exactly one `SELECT` against `model_cls` regardless of host count —
use a query-counting fixture (SQLAlchemy event hook on `before_cursor_execute`
against a test DB session) with, say, 50 hosts' worth of results and assert
the count is O(1) not O(hosts). This is a real regression test, not
theater, because this bug already happened once.

### 3. Concurrency invariant tests

These test _structural_ guarantees, not timing — don't write a flaky test
that depends on thread scheduling order.

- **No live ORM object reaches `_work()`:** for `run_sync`/`run_multi_sync`,
  assert the `host_data` list passed into the thread pool is built from
  plain tuples (`(int, str)`), not `Host` instances — a type-level
  assertion (`isinstance` check in the test) on what's actually queued to
  `executor.submit`, not an inference from behavior.
- **All results are collected before any DB write starts:** mock/spy on
  `session_scope` and assert it's invoked zero times until every future in
  `as_completed()` has resolved.
- **A single collector exception doesn't abort the whole sync:** feed
  `run_sync` a fake collector that raises for host #3 of 5 → assert hosts
  1,2,4,5 still get written, host 3 appears in the `errors` list with
  `kind="collect"`, and `failed` count is exactly 1 — not 5, not 0.
- **SSH connect failure vs collection failure are distinguished:** assert
  `kind` is `"ssh"` when `ssh_mod.connect` raises, `"collect"` when the
  collector itself raises after a successful connect — downstream
  audit/failure persistence depends on this distinction being correct.
- **`client.close()` is always called**, success or failure path — spy on
  the fake `SSHClient.close` and assert call count equals host count
  regardless of how many hosts failed.

### 4. `ssh.py` — host key policy, must be tested per mode explicitly

- `strict_host_key_checking: true`, no known_hosts entry for the host →
  raises `SSHException` with the `ssh-keyscan` hint in the message, never
  attempts to connect
- `strict_host_key_checking: true`, known_hosts entry present and matches
  → `RejectPolicy` set, connects normally
- `strict_host_key_checking: true`, known_hosts entry present but the
  server presents a _different_ key → `BadHostKeyException` caught and
  re-raised as `SSHException` with the changed-key message, not a bare
  paramiko exception leaking out
- `strict_host_key_checking: new`, no known_hosts entry → connects via
  `AutoAddPolicy`. **This is where the flagged gap lives — write a test
  that asserts the key is actually persisted to `known_hosts_path` after a
  successful connect.** If `save_host_keys()` isn't being called, this
  test should currently fail — that's the point; it turns the known gap
  into a tracked regression instead of a comment.
- Invalid `strict_host_key_checking` value (typo in config) → raises
  `ValueError` before any connection attempt, not a fallback to a default
- Retry logic: `AuthenticationException` is raised on attempt 1 of 3
  configured retries → no retry attempted, fails immediately (confirm
  `_NO_RETRY` is actually respected, not just present in code)
- A transient `SSHException` (not auth, not bad host key) on attempt 1 →
  retried, succeeds on attempt 2, final result is success with no error
  surfaced

### 5. Config loading tests (`lib/config.py`)

- Missing `credentials.<name>` referenced by `ssh.credential` → `KeyError`
  with the credential name in the message, not a generic lookup error
- `satellite` block entirely absent from config → `get_satellite_settings`
  raises `KeyError` naming `'satellite'`, and confirm `sync.py`'s
  `sync foreman` command catches this specific `KeyError` and produces the
  friendly `click.ClickException` — this is a cross-module test worth
  having since the friendly error message is the whole point.
- Config file loaded once and cached (`_cfg` global) — test that a second
  call to `load_config()` doesn't re-read the file (spy on `open`).

### Fixtures to build once, reuse everywhere

- `FakeSSHClient` — a minimal stand-in for `paramiko.SSHClient` whose
  `exec_command(cmd)` returns canned `(stdin, stdout, stderr)` from a
  dict keyed by command string (or a substring match), so collector tests
  don't need a real SSH server. `stdout` needs to support iteration
  (`for line in stdout`) and `.read().decode()`, matching how the real
  collectors consume it — check both usage styles are supported since
  different collectors use different consumption patterns (`disks.py`
  uses `.read()`, `mounts.py` iterates line-by-line).
- Real captured command output as fixture files (`tests/fixtures/lsblk.json`,
  `tests/fixtures/etc_group`, `tests/fixtures/systemctl_show.txt`, etc.)
  pulled from actual RHEL and Debian hosts — not hand-typed approximations.
  If you don't have access to both, at minimum capture from whatever real
  Linux boxes you do have; synthetic fixtures are exactly the "theater"
  this section exists to avoid, since a hand-typed fixture tends to already
  match whatever the parser expects.
- In-memory or ephemeral Postgres (testcontainers, or a local throwaway DB
  via `TPA_CONFIG` pointed at a test database) for `_write_back`,
  `match_hosts`, and migration tests — do not mock SQLAlchemy's session
  for upsert-logic tests; the whole point of these tests is catching real
  SQL/constraint behavior (unique constraint violations, JSONB round-trips),
  which a mocked session cannot catch.

### What "done" looks like for a test suite change

A new collector or merge-logic change is not adequately tested until:

- At least one fixture-based test exists using output that could plausibly
  come from a real, slightly-unusual target host (older tool version,
  missing field, unexpected null) — not just the clean/expected case.
- At least one test exists for the failure/malformed-input path, asserting
  graceful degradation (empty list/`None`), not just the success path.
- If the change touches `sync_runner.py`, `sync.py`, or `synchosts.py`: the
  concurrency invariant tests in section 3 still pass unmodified — if you
  had to change one of those tests to make your change pass, that's a
  signal you may have reintroduced the ORM-across-threads or per-host-query
  regression; investigate before proceeding, don't just update the test to
  match.
