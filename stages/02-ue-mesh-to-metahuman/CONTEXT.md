# Stage 02 — ue-mesh-to-metahuman

Run the Python driver inside a live UE 5.6 Editor to turn the normalized
mesh + texture into a rigged MetaHuman Character asset. Operator
pre-conditions: UE 5.6 open with the project from `_config/pipeline.yaml`,
MetaHuman + MetaHumanAnimator + MetaHumanCharacter plugins enabled, and
a valid Epic Auto Rig Service login (one-time per session).

## Inputs

| path                                                | notes                                      |
|-----------------------------------------------------|--------------------------------------------|
| `scans/<id>/01-normalized/mesh.obj`                 | canonical mesh from stage 01               |
| `scans/<id>/01-normalized/texture.jpg`              | canonical diffuse texture                  |
| `scans/<id>/01-normalized/scan_manifest.json`       | metadata; used for manifest chaining       |
| `_config/pipeline.yaml`                             | `ue.project`, `content_subpath`            |
| `skills/ue-metahuman-python.md`                     | reference for the API surface              |

## Process

1. Operator opens the UE project, confirms the three MH plugins are
   loaded, signs into Auto Rig Service once (see skills reference).
2. Operator invokes the driver from the UE Python console:

   ```python
   py "C:/Users/smorc/Scan to Metahuman/stages/02-ue-mesh-to-metahuman/tools/run_scan.py" --scan <id>
   ```

3. The driver:
   - Reads `_config/pipeline.yaml`.
   - Imports `mesh.obj` into `/Game/<content_subpath>/<id>/ScanMesh`.
   - Creates a `MetaHumanIdentity` asset at
     `/Game/<content_subpath>/<id>/MHI_<id>`, attaches the scan mesh as
     the face part neutral pose.
   - Starts the frame tracking pipeline; polls
     `is_frame_tracking_pipeline_processing` until False, up to
     `tracking_timeout_seconds`.
   - Calls `diagnostics_indicates_processing_issue`; aborts with a
     readable error if non-zero.
   - Calls `face.conform()`.
   - Creates / opens a `MetaHumanCharacter` asset at
     `/Game/<content_subpath>/<id>/MHC_<id>` seeded from the Identity.
   - Calls `UMetaHumanCharacterEditorSubsystem.request_auto_rigging(...)`
     with retry-on-transient-error.
   - Calls `request_texture_sources(...)`.
4. On success: writes `scans/<id>/02-metahuman/metahuman_manifest.json`
   with all UE asset paths and marks the stage `done` in the scan
   manifest. On any failure marks the stage `failed` with the error.

## Outputs

| path                                                      | notes                                         |
|-----------------------------------------------------------|-----------------------------------------------|
| `scans/<id>/02-metahuman/metahuman_manifest.json`         | UE project + asset paths for Stage 01 of the sibling MH->GLB pipeline |
| (inside the UE project) `/Game/<content_subpath>/<id>/ScanMesh` | imported static mesh                          |
| (inside the UE project) `/Game/<content_subpath>/<id>/MHI_<id>` | MetaHumanIdentity asset                       |
| (inside the UE project) `/Game/<content_subpath>/<id>/MHC_<id>` | MetaHumanCharacter asset, rigged              |

`metahuman_manifest.json` schema:

```json
{
  "scan_id": "person-3",
  "ue_project": "C:/.../MetaHumans.uproject",
  "content_subpath": "ScanCaptures/person-3",
  "scan_mesh_asset": "/Game/ScanCaptures/person-3/ScanMesh",
  "identity_asset": "/Game/ScanCaptures/person-3/MHI_person-3",
  "character_asset": "/Game/ScanCaptures/person-3/MHC_person-3",
  "auto_rig_commit": "<epic cloud solve id if exposed>",
  "completed_at": "<ISO 8601>"
}
```

## Verification

A passing stage means:
- `metahuman_manifest.json` exists and parses as above.
- The three listed UE assets exist in the project (operator check if needed).
- `manifest.json` stages["02-ue-mesh-to-metahuman"].status == "done".

## Known caveats

- UE 5.6 MetaHuman Python bindings cover these steps but exact class
  and method names are still being stabilised. When in doubt, compare
  against Epic's shipped examples at
  `Engine/Plugins/MetaHuman/MetaHumanAnimator/Content/Python/`.
- Auto-rig cloud service is flaky. Default retry: 3 attempts with
  exponential backoff (2s, 4s, 8s).
- If the Editor session has no Auto Rig login, `request_auto_rigging`
  returns a login-error status; driver fails early with a readable
  message telling the operator to log in.
