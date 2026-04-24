# CONTEXT.md — Scan to Metahuman (Layer 1: task routing)

Pick a scan id. Walk its stages in order. Each stage has its own contract at
`stages/<NN>-*/CONTEXT.md`. Do not load stages you are not currently running.

## Stage map

| NN | folder                       | Input                         | Output                                    |
|----|------------------------------|-------------------------------|-------------------------------------------|
| 01 | normalize-scan               | `scans/<id>/source/*`         | `scans/<id>/01-normalized/`               |
| 02 | ue-mesh-to-metahuman         | `scans/<id>/01-normalized/`   | `scans/<id>/02-metahuman/` + MH in UE project |

After stage 02 the sibling `Metahuman to GLB` pipeline takes over: its Stage 01
reads from the UE project, its Stages 02 and 03 produce the final GLB.

## Per-scan folder conventions

```
scans/<id>/
├── manifest.json               one record per stage, status + paths
├── source/                     original upload, kept as received
├── 01-normalized/
│   ├── mesh.obj
│   ├── texture.jpg | texture.png
│   └── scan_manifest.json      format, tri count, source chain
└── 02-metahuman/
    └── metahuman_manifest.json UE project path, identity asset path, MH asset path
```

## Manifest schema

`scans/<id>/manifest.json`:

```json
{
  "id": "<scan id>",
  "created": "<ISO 8601>",
  "source_upload": "<filename as received>",
  "stages": {
    "01-normalize-scan": {
      "status": "pending | running | done | failed",
      "started": "...",
      "finished": "...",
      "outputs": { "mesh": "01-normalized/mesh.obj", "texture": "..." },
      "error": null
    },
    "02-ue-mesh-to-metahuman": { "status": "pending", ... }
  }
}
```

## Orchestration invocation

For scan `<id>` at stage `<NN>`, spawn a Haiku agent with:
- prompt = `stages/<NN>-*/CONTEXT.md` + `scans/<id>/` + any files the stage's
  Inputs table names.
- tools = only what's in `stages/<NN>-*/tools/`.
- model = `claude-haiku-4-5`.
