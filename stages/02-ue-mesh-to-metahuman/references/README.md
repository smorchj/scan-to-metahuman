# Stage 02 references

Concrete UE 5.6 MetaHuman Python API surface is not completely documented
as of 2026-04-24. When `run_scan.py` fails on a specific call, compare
against Epic's shipped examples — they are the load-bearing source of
truth for how the in-editor Python bindings are actually shaped.

## Files to open before editing the driver

Inside your UE 5.6 install:

```
Engine\Plugins\MetaHuman\MetaHumanAnimator\Content\Python\create_capture_data.py
Engine\Plugins\MetaHuman\MetaHumanAnimator\Content\Python\create_identity_for_performance.py
Engine\Plugins\MetaHuman\MetaHumanCharacter\Content\Python\examples\
```

`create_identity_for_performance.py` is the most relevant. It:
- Creates a `MetaHumanIdentity` asset programmatically.
- Adds a face part.
- Feeds a neutral pose (their example uses a take of video; we feed a
  static mesh instead via `set_neutral_pose_from_static_mesh`, which is
  the only method that differs from their example).
- Runs `start_frame_tracking_pipeline` + polls + `conform`.

## Sites in run_scan.py marked `API NOTE`

Each one references a plugin call whose signature is likely stable but
where Epic has not published a final doc page. Verify against the
shipped example before touching. The sites are:

1. `MetaHumanIdentityFactoryNew()` class name
2. `unreal.MetaHumanIdentity` asset class
3. `find_or_add_part_of_class` + `MetaHumanIdentityFace`
4. `set_neutral_pose_from_static_mesh`
5. `start_frame_tracking_pipeline` / `is_frame_tracking_pipeline_processing`
6. `diagnostics_indicates_processing_issue`
7. `face_part.conform()`
8. `MetaHumanCharacterFactoryNew()`
9. `unreal.MetaHumanCharacter` asset class
10. `MetaHumanCharacterEditorSubsystem.seed_from_identity`
11. `request_auto_rigging` return-type (checking `.success` / `.commit_id`)
12. `request_texture_sources` signature

If any of these differ in your plugin version, edit the marker and keep
the rest intact.

## Useful docs

- https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Plugins/MetaHumanIdentity
- https://dev.epicgames.com/documentation/metahuman/python-scripting-for-metahuman-creator
- https://dev.epicgames.com/documentation/en-us/unreal-engine/BlueprintAPI/MetaHuman/AutoRigging/LogintoAutoRigService
