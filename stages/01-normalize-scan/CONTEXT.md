# Stage 01 — normalize-scan

Take an arbitrary upload and produce a canonical mesh + texture pair at
`scans/<id>/01-normalized/`. The goal is that Stage 02 never has to think
about where the files came from.

## Inputs

| path                                   | notes                                             |
|----------------------------------------|---------------------------------------------------|
| `scans/<id>/source/*`                  | original upload. One of:                          |
|                                        |  - a `.zip` (Sketchfab, Polycam export, etc.)     |
|                                        |  - a loose `.obj` + mtl + texture                 |
|                                        |  - a `.fbx`, `.ply`, `.glb`, or `.usdz`           |
| `_config/pipeline.yaml`                | read `normalize.max_tris`, `normalize.max_texture_px`, `normalize.accept_formats` |

## Process

Run the single launcher:

```bash
python stages/01-normalize-scan/tools/normalize.py --scan <id>
```

The tool:

1. Resolves `scans/<id>/source/` relative to the repo root.
2. If the only file is a `.zip`, extracts it to a temp dir. If the
   extracted contents contain another `.zip` (Sketchfab's
   `source/Person.zip.zip` pattern), extracts that too (one level
   recursive, no deeper).
3. Searches the extracted tree for all meshes in `accept_formats`.
   Picks the one with the largest file size as the primary.
4. Searches the tree for the primary texture. Priority order:
   - A file referenced by the primary mesh's sidecar (`.mtl` for OBJ,
     texture listed in gltf buffers, etc.).
   - If nothing sidecar-linked, the largest image by file size among
     `.png`, `.jpg`, `.jpeg`, `.webp`.
5. Copies the mesh to `scans/<id>/01-normalized/mesh.<ext>` and the
   texture to `scans/<id>/01-normalized/texture.<ext>` (original
   extensions preserved).
6. For OBJ inputs, rewrites the `.mtl` so its `map_Kd` line references
   the local `texture.<ext>` (Stage 02 is stricter about sidecar paths
   than UE's usual import).
7. Counts triangles. If above `max_tris`, still writes the output but
   flags `oversized: true` in the scan manifest.
8. Writes `scans/<id>/01-normalized/scan_manifest.json` with format,
   original path, triangle count, texture dimensions, and checksum of
   both files.
9. Updates `scans/<id>/manifest.json` `stages["01-normalize-scan"]`
   to `status=done` on success, `status=failed` with `error` on any
   failure.

## Outputs

| path                                                    | notes                                  |
|---------------------------------------------------------|----------------------------------------|
| `scans/<id>/01-normalized/mesh.<ext>`                   | primary mesh, format preserved         |
| `scans/<id>/01-normalized/texture.<ext>`                | primary texture, format preserved      |
| `scans/<id>/01-normalized/mesh.mtl` (OBJ only)          | rewritten to reference local texture   |
| `scans/<id>/01-normalized/scan_manifest.json`           | per-scan metadata                      |

`scan_manifest.json` schema:

```json
{
  "scan_id": "person-3",
  "source_upload": "person-3.zip",
  "primary_mesh": { "path": "mesh.obj", "format": "obj", "triangles": 123456 },
  "primary_texture": { "path": "texture.jpg", "format": "jpg", "width": 2048, "height": 2048 },
  "oversized": false,
  "notes": []
}
```

## Verification

A passing stage means:

- `01-normalized/mesh.*` exists and is one of `accept_formats`.
- `01-normalized/texture.*` exists.
- `scan_manifest.json` parses as the schema above.
- `manifest.json` stages["01-normalize-scan"].status == "done".

If any of these fail, the stage is not done.
