# UE 5.6 MetaHuman Python API surface (stable reference)

Use this as the load-bearing reference when editing or writing Stage 02's
Python driver. Cross-check any claim against Epic's shipped examples at:

- `Engine/Plugins/MetaHuman/MetaHumanAnimator/Content/Python/create_capture_data.py`
- `Engine/Plugins/MetaHuman/MetaHumanAnimator/Content/Python/create_identity_for_performance.py`
- `Engine/Plugins/MetaHuman/MetaHumanCharacter/Content/Python/examples/`

## Plugins required (all engine-bundled in 5.6)

- MetaHuman
- MetaHumanAnimator
- MetaHumanCharacter

## Step → API

1. **Import OBJ as Static Mesh**
   - `unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])`
   - `task = unreal.AssetImportTask()` with `.filename`, `.destination_path`,
     `.automated=True`, `.save=True`, `.replace_existing=True`.

2. **Create MetaHumanIdentity**
   - `UMetaHumanIdentity` UCLASS, exposed as `unreal.MetaHumanIdentity`.
   - Create via asset tools factory; add a face part; attach the imported
     static mesh as the neutral pose.

3. **Landmark tracking**
   - `identity.start_frame_tracking_pipeline(...)`
   - `identity.is_frame_tracking_pipeline_processing()` — poll until False.
   - `identity.diagnostics_indicates_processing_issue()` — check for failure.
   - `face_part.conform()` — fits the canonical MetaHuman topology.

4. **Cloud solve (Mesh to MetaHuman)**
   - `UMetaHumanCharacterEditorSubsystem.request_auto_rigging(character, params)`
   - Login required once per Editor session via the `LoginToAutoRigService`
     Blueprint node or its Python equivalent. Operator does this manually
     the first time; session is persistent afterwards.

5. **Ingest textures**
   - `UMetaHumanCharacterEditorSubsystem.request_texture_sources(character)`

## Known issues (5.6)

- Auto-rig cloud service has intermittent outages. Wrap `request_auto_rigging`
  in retries with backoff.
- The "multiple promoted frames" Python API bug does not apply to single-scan
  identity creation (one neutral pose only).
- Quixel Bridge is not Python-scriptable. The modern `UMetaHumanCharacter`
  workflow bypasses Bridge; keep everything inside the subsystem.

## UE 5.7 note

5.7 (preview as of 2026-04-24) formalizes the MetaHuman Creator Python /
Blueprint API with broader bindings. If the 5.6 surface proves unstable,
upgrading is a realistic option. Docs for 5.7 are incomplete during preview.

## Useful links

- https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Plugins/MetaHumanIdentity
- https://dev.epicgames.com/documentation/metahuman/python-scripting-for-metahuman-creator
- https://dev.epicgames.com/documentation/en-us/unreal-engine/BlueprintAPI/MetaHuman/AutoRigging/LogintoAutoRigService
