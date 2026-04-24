# Scan to Metahuman

Deterministic pipeline that turns an arbitrary 3D face scan into a
MetaHuman in an Unreal 5.6 project, automated from Python inside the
UE Editor. Designed to be the upstream stage of the sibling
[metahuman-to-glb](https://github.com/smorchj/metahuman-to-glb) pipeline,
so the full end-to-end flow is:

    scan upload → normalize → UE Mesh-to-Metahuman → (MH→GLB) → web gallery

## Stages

- **01 normalize-scan** — accept any upload layout (Polycam, RealityScan,
  Sketchfab nested zip, etc.), pick the primary OBJ + texture, write a
  canonical `01-normalized/` folder with a manifest.
- **02 ue-mesh-to-metahuman** — Python driver run from inside a live UE
  5.6 Editor: imports the OBJ, creates a MetaHumanIdentity, runs landmark
  tracking and conform, submits to the cloud auto-rig service, downloads
  texture sources. Operator does the Epic OAuth login once per session;
  per-scan runs are unattended.

## How it is wired

Same ICM (Interpretable Context Methodology) structure as the sibling
`metahuman-to-glb` repo: each stage has its own `CONTEXT.md` contract so
a narrow executor (Haiku) can run a stage with only that stage's files
plus the current scan folder in context. Opus designs the contracts.

## Run a scan

```bash
# One-time: put the upload (zip or folder) somewhere and pick an id.
mkdir -p "scans/<id>/source"
cp path/to/upload.zip "scans/<id>/source/"

# Stage 01 (plain Python, no UE):
python stages/01-normalize-scan/tools/normalize.py --scan <id>

# Stage 02 (inside UE 5.6 Editor, Python console):
py stages/02-ue-mesh-to-metahuman/tools/run_scan.py --scan <id>
```

Once Stage 02 finishes, the character exists in the UE project configured
in `_config/pipeline.yaml`. Hand off to the MH→GLB pipeline.

## License

MIT.
