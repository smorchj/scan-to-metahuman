# CLAUDE.md — Scan-to-Metahuman Pipeline Agent Orientation

You are an agent operating inside an **Interpretable Context Methodology (ICM)**
workspace. This file is Layer 0: system orientation. Same pattern as the sibling
`Metahuman to GLB` repo — read its CLAUDE.md if you need the conceptual
background on ICM; the rules below are identical.

## What this workspace does

Takes an arbitrary 3D face scan (Polycam / RealityScan / Sketchfab / etc.) and
produces a MetaHuman in a configured UE 5.6 project, automated with Python
driven from inside the UE Editor. The hand-off point to the existing
`Metahuman to GLB` pipeline is the completed MetaHuman asset in that UE project.

  scan upload → 01 normalize → 02 UE Mesh-to-MetaHuman → (existing MH→GLB pipeline)

## How the workspace is organized

- `CONTEXT.md` (root)          — Layer 1: task routing. Read first.
- `_config/pipeline.yaml`       — Layer 3: config shared across stages
                                 (UE path, project path, scan queue folder, etc.)
- `skills/*.md`                 — Layer 3: stable reference (UE MetaHuman Python
                                 API surface, MP plugin versions, etc.)
- `stages/<NN>-<name>/`         — one stage per numbered folder, strict boundary
  - `CONTEXT.md`                — Layer 2: the stage contract (Inputs / Process /
                                 Outputs)
  - `tools/`                    — scripts the stage runs
  - `references/`               — stage-specific reference files
- `scans/<id>/`                 — Layer 4: per-scan working artifacts
  - `manifest.json`             — per-scan status, one record per stage
  - `source/`                   — original upload (kept as received)
  - `01-normalized/`            — canonical mesh + texture + scan_manifest.json
  - `02-metahuman/`             — UE asset paths + metahuman_manifest.json

## Context discipline (the rule)

When working on stage N, **only load** that stage's `CONTEXT.md` + files it names
in its Inputs table + the current scan's `scans/<id>/` folder. Do not load other
stages. This keeps total context low enough for Haiku to execute reliably.

Opus designs and edits the contracts. Haiku runs them.

## Spawning a Haiku agent for one stage

From the root `CONTEXT.md`, the orchestration pattern is:

  For scan <id> at stage <NN>:
    prompt = stages/<NN>-*/CONTEXT.md + scans/<id>/ + stage's Inputs files
    tools  = only tools in stages/<NN>-*/tools/
    model  = claude-haiku-4-5

Haiku's job is narrow: read Inputs table, invoke the stage's one launcher
script, verify outputs match the Outputs table, update `scans/<id>/manifest.json`.

## Rules

- Scripts are deterministic Python. LLMs glue, they don't transform geometry.
- Every stage writes a machine-readable manifest. No stage reads another stage's
  internals.
- Fail loud with actionable messages. Never silently skip.
- Stage 02 requires a running UE Editor with the MetaHuman + MetaHumanAnimator
  + MetaHumanCharacter plugins and a live Epic auto-rig login. That is operator
  setup, not agent work.
