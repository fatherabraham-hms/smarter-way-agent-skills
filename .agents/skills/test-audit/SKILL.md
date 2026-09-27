---
name: test-audit
description: Gate new tests, and audit low-value or implementation-coupled tests and the test-only seams they require.
disable-model-invocation: true
---

# Test Audit

Three modes, one value bar. Authoring mode gates every new or changed test at
write time. Audit mode sweeps tests that re-assert source, duplicate stronger
proof, couple behavior to implementation, or keep test-only production seams
alive. Continue a broad audit as separate coherent follow-up PRs. Optimize for
confidence. Before a campaign that prunes one whole subsystem's test surface,
read [CAMPAIGN.md](CAMPAIGN.md).

## Authoring gate

Before adding any test, answer four questions. A missing answer means do not
add it yet:

1. What observable behavior, invariant, or independent contract does it protect?
2. What credible regression makes it fail?
3. Why does existing coverage not already catch that failure? Each contract has
   one primary test owner at the strongest boundary. Another layer needs its
   own distinct risk, such as a transport or lifecycle failure the owner cannot
   reach. Prefer extending a table-driven case or shared fixture over a
   near-duplicate test. Consolidate duplicated setup in the same change.
4. Does it need a production seam (export, flag, wrapper, injection hook) that no
   production caller needs? If yes, move the test to the real boundary instead.

Then check the test against every [junk pattern](#junk-patterns). A match fails
the gate unless the [retention bar](#retention-bar) names the contract it
independently guards. A test that would break under behavior-preserving
refactoring is asserting implementation. Rewrite it at the owning boundary
before landing it.

A bug regression must fail on the pre-fix code for the intended reason and
pass after the owner-boundary repair. A regression that never demonstrably
failed proves the mock. One regression at the owner boundary covers the bug.

Done when every new or changed test has all four answers and passes the junk
check, or it is not added.

## Junk patterns

The shared checklist for both modes. The authoring gate rejects a new test that
matches one. Audits hunt for existing tests that do.

- assertion-free coverage probes
- self-comparisons and identity copiers
- copied fixtures, inventories, manifests, or export lists
- exact source, import, or string greps
- private predicate or call-shape tests duplicated at real boundaries
- duplicate invocations of the same contract
- provider-local replays of shared helpers
- tests whose only purpose is preserving test-only exports, globals, or wrappers
- dead production code whose only callers are tests
- expected values produced by the helper or renderer under test
- mocks that implement the asserted behavior, or one identical mock standing in
  for different APIs
- fixtures that supply the receipt, admission, or callback ordering the owner
  should produce, or persistence asserted against a store the path never writes
- capability tests that restate declared flags instead of exercising the
  delivery or acknowledgement the flag promises
- negative controls that pass for an unrelated reason, such as a denial from a
  different guard or a rejection the production path never reaches
- names or fixtures that promise more than the input exercises, such as a
  "retires the window" test asserting the window was not cleared

## Value bar

Tests justify their maintenance cost by protecting behavior, a credible
regression, or an independently meaningful contract. In an audit, an existing
test that must change for behavior-preserving source reorganization is suspect.
The authoring gate still rejects new ones.

Before judging a candidate, read the complete test and production owner, its
entry point, callers, callees, sibling implementations, overlapping tests, CI
routing, and relevant history. Read root and scoped `AGENTS.md` files first.
When the test claims dependency-backed behavior, inspect the dependency source
or types directly.

## Discovery

Keep discovery read-only. Report evidence before editing. For a broad scope,
run parallel discovery lanes when subagents are available. Split lanes along
the checkout's real boundaries (core, packages, plugins, UI, apps, scripts,
tooling) plus one cross-cutting pattern sweep.

Outside campaign mode, prefer a few high-confidence candidates over a large
speculative inventory. Hunt for the [junk patterns](#junk-patterns).

Done when each candidate has a location and the junk pattern it matches, and
no file has been edited.

## Retention bar

Keep a test when it independently enforces a public API, plugin SDK, protocol,
config, migration, storage, security, platform, default, prompt-byte, generated
cross-language, package, release, or architecture contract. Also keep:

- call ordering when order is observable behavior
- regressions with a credible failure mode
- source inspection when it is the cheapest independent guard: it fails when
  the contract changes (the user-facing key, byte, or path) and survives an
  identifier-only refactor
- a retained test that fails on the baseline: treat it as a possible product
  bug, reproduce it, and repair the owner

Static or slow is not a deletion reason. A test that resembles implementation
may still be the independent contract. Prove otherwise before removing it.

## Candidate evidence

Record every field below before editing. A missing field means the candidate is
not ready for deletion:

- exact test name and location
- what failure it can actually detect
- non-test callers of the covered production or support seam
- stronger remaining owner-boundary proof, or why no proof is needed
- relevant history and the reason the test or seam exists
- production or test-support deletion unlocked
- risk and the focused validation command

Done when every field is filled for each candidate you will edit.

## Edit shape

Choose one coherent owner-boundary batch. Delete obsolete test-only exports,
globals, wrappers, and dead production paths. Move retained regressions to
their canonical owners. Consolidate repeated package or dependency assertions
into one generic contract.

Prefer net-negative production LOC. Leave uncertain candidates in place.

Done when one owner-boundary batch is chosen and every edit in it belongs to
that owner.

## Validation

Leave the checkout's test runner idle before editing source or tests. Infer
the test command, formatter, and changed-file gate from the repo (`AGENTS.md`,
package scripts, Makefile, or the equivalent). Use those commands.

1. Run the smallest owner and sibling tests.
2. For a removed source grep or plan assertion, run the executable or dry-run
   that owns the real contract.
3. Run the formatter on the touched files, then `git diff --check`.
4. Run the checkout's changed-file gate when one exists.
5. Inspect `git diff --numstat`. Report production and tooling separately from
   tests and test support.
6. After the final audit edits, run `/compr-code-review`.

Done when the focused proof has run and the numstat split is recorded.

## Landing and continuation

Commit, push, or open a PR only when the user authorizes it. Use
`/smart-commit-to-pr` for that landing. Land one coherent change at a time.
After it lands, refresh from the current default branch and rerun read-only
discovery for the next high-confidence batch.

Done when the handoff is delivered, and any authorized landing is one coherent
PR.

## Handoff

Report:

- root cause and removed low-value categories
- production owner simplifications
- retained false positives and why they remain valuable
- focused and full proof actually run
- production versus test LOC
- PR and merge state
- named follow-ups

Done when the report covers every item above.
