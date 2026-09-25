---
name: audit-plan
description: Audit one plan on five axes and roll up a Pass or Revise report.
disable-model-invocation: true
---

# audit-plan

## 1. Resolve the plan set

The plan set is the plan plus files it relies on (linked blueprint, glossary, flow diagram).

Open the first match:

1. A path or attachment the user named.
2. Frontmatter `arch_blueprint:` on a named plan, or `cursor_plan:` on a named blueprint. Read both when either pointer is present.
3. When `plans_path` is set in `$XDG_CONFIG_HOME/smarter-way/config.json`, else `$HOME/.config/smarter-way/config.json`: the recipe under that root the user named. Expand `~` and environment variables. Read `plans_path` only from that file.

Done when every file in the plan set has an absolute path. When no plan can be opened, say so and stop.

## 2. Classify

Fill the dispatch card before any pass starts.

| Fact | Values | Decide |
|------|--------|--------|
| Field | `brownfield` or `greenfield` | Brownfield when the plan changes a codebase you can open. Greenfield when the system has no code yet. |
| Scope | `minor-bugfix` or `larger` | `minor-bugfix` when the plan is a local defect fix with no new flow, module, or contract. Otherwise `larger`. |
| UI | `present` or `absent` | `present` when the plan adds or changes a screen, component, or other user-visible surface. |

Done when the card lists the plan-set paths, the codebase root when brownfield, and field, scope, and UI.

## 3. Dispatch

Launch five subagents in one parallel dispatch. Paste the card and that axis's numbered rules, unchanged, into each prompt. The pass reads the plan set from those paths.

Return this shape only:

```text
Axis: <name>
Verdict: Pass | Fail
Rules:
- <n> | Pass | Fail | N/A | <file:line or heading> | <one sentence>
```

One line per rule. Security rule 1 adds one line per gap. `N/A` only when that rule's condition is off. A missing required section is Fail.

Done when five reports are back.

### Feasibility

Apply the rule for `field`. Mark the other N/A.

1. Brownfield: the plan cites the modules it changes as paths or symbols you can open. A cited path missing from the tree is Fail.
2. Greenfield:
   - Vague — a requirement with no artifact or observable outcome.
   - Verbose — a passage that restates another and adds no constraint, artifact, or decision.
   - Conflict — quote both sides.

### Performance and scalability

1. When scope is `larger`, the plan has ordered phases and a quality gate on each phase. A gate names an observable check and the evidence that proves it. "Make sure it scales" is Fail. When scope is `minor-bugfix`, N/A.
2. The plan keeps a modular, pluggable architecture. `minor-bugfix` passes when the change keeps existing module boundaries. `larger` names the seams and what swaps without editing callers.
3. Domain-modeling review: challenge each term against the glossary, name a precise replacement for any fuzzy term, give one scenario that breaks a boundary between two terms, and cross-check claims against code when brownfield.

### Security

Read [owasp-top-10.md](owasp-top-10.md). Apply every category.

1. A gap that violates the OWASP Top 10 is Fail. Cite the category id on each gap.
2. Unprotected credentials, PII, or API keys are Fail. Count a secret written in the plan, and a design that stores or transmits them with no stated protection.
3. The plan has an explicit section listing possible security vulnerabilities. Quote its heading.

### Logical continuity

1. The flow is a mermaid diagram in its own file. Open it and check it matches the plan's flow. An inline fence is Fail.
2. The plan set includes a glossary (a section or a linked file).
3. Trace one end-to-end data path and, when UI is present, one user path. Name any break, loop with no exit, or step whose input the previous step does not produce.
4. Entity names describe this system. Fail a name that could belong to another system, or two names for one concept.
5. The modules in the architecture section are the modules in the diagram and the glossary.

### Testability

1. The plan names unit tests and what a failure looks like.
2. When UI is `present`, the plan names each surface and the assertion. When `absent`, N/A.
3. When brownfield, the plan names existing behavior the change must leave intact. When greenfield, N/A.

## 4. Repair

Confirm each cited location exists. Accept the pass's Pass, Fail, or N/A. Re-dispatch an axis once when a rule line is missing or the location is not in the plan set.

Done when every rule on every axis has a line and the location checks out.

## 5. Roll up

Write the report yourself. Deduplicate one gap that several axes hit, and keep every axis on that row. An axis is Fail when any of its rules is Fail. The plan is **Revise** when any axis is Fail, otherwise **Pass**. List Fail, then Pass, then N/A.

```markdown
# Plan audit: [title]

## Summary
[Pass or Revise]. [field], [scope], UI [present or absent].
[The strongest gap, or why the plan holds.]

## Plan set
| Role | Path |
|------|------|
| Plan | |
| Diagram | |
| Glossary | |

## Axis rollup
| Axis | Verdict | Failed rules |
|------|---------|--------------|
| Feasibility | | |
| Performance and scalability | | |
| Security | | |
| Logical continuity | | |
| Testability | | |

## Findings
| Axis | Rule | Location | Result | Evidence |
|------|------|----------|--------|----------|

## Verdict
**Pass** or **Revise** — what must change before implementation.
```

Done when the report is in the reply and the plan set is unchanged.
