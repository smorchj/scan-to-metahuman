"""Stage 02 driver: scan mesh -> rigged MetaHuman Character.

Intended to be invoked from a running UE 5.6 Editor's Python console:

    py "<repo>/stages/02-ue-mesh-to-metahuman/tools/run_scan.py" --scan <id>

Pre-conditions (operator):
  1. Open the UE project listed at _config/pipeline.yaml -> ue.project.
  2. Ensure the MetaHuman, MetaHumanAnimator, MetaHumanCharacter plugins
     are enabled.
  3. Log into the Epic Auto Rig Service once per session.

Reference: skills/ue-metahuman-python.md. Concrete API names track Epic's
shipped examples at:
    Engine/Plugins/MetaHuman/MetaHumanAnimator/Content/Python/
      create_capture_data.py
      create_identity_for_performance.py
    Engine/Plugins/MetaHuman/MetaHumanCharacter/Content/Python/examples/

If a call signature below diverges from your installed plugin version,
update the sites marked with `API NOTE` and re-run. The logic is
isolated enough that only those sites should need touching.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

try:
    import unreal  # available inside the UE Editor's Python runtime
except ImportError as e:
    print(
        "run_scan: this script must be executed from inside the UE Editor's "
        "Python runtime. `unreal` module not available.",
        file=sys.stderr,
    )
    raise

try:
    import yaml  # PyYAML
except ImportError:
    # UE ships a Python that may not have PyYAML; fall back to our own tiny parser.
    yaml = None


RETRY_DELAYS = (2, 4, 8)


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(workspace: Path) -> dict:
    cfg_path = workspace / "_config" / "pipeline.yaml"
    text = cfg_path.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text)
    return _dumb_yaml(text)


def _dumb_yaml(text: str) -> dict:
    """Two-level YAML good enough for our config. No lists, no anchors."""
    out: dict = {}
    stack: list[tuple[int, dict]] = [(-1, out)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if not val:
            child: dict = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            if val.lower() in ("true", "false"):
                parent[key] = (val.lower() == "true")
            elif val == "null":
                parent[key] = None
            else:
                try:
                    parent[key] = int(val)
                except ValueError:
                    try:
                        parent[key] = float(val)
                    except ValueError:
                        parent[key] = val
    return out


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

def update_scan_manifest(scan_dir: Path, status: str,
                         outputs: dict | None = None,
                         error: str | None = None) -> None:
    path = scan_dir / "manifest.json"
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if path.exists():
        m = json.loads(path.read_text(encoding="utf-8"))
    else:
        m = {"id": scan_dir.name, "created": now, "stages": {}}
    stage = m["stages"].setdefault("02-ue-mesh-to-metahuman", {"status": "pending"})
    if status == "running" and "started" not in stage:
        stage["started"] = now
    stage["status"] = status
    if status in ("done", "failed"):
        stage["finished"] = now
    if outputs is not None:
        stage["outputs"] = outputs
    if error is not None:
        stage["error"] = error
    path.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# UE asset ops
# ---------------------------------------------------------------------------

def import_scan_mesh(normalized_dir: Path, asset_path: str) -> "unreal.StaticMesh":
    """Import mesh.obj as a Static Mesh at asset_path. Deterministic."""
    mesh_file = normalized_dir / "mesh.obj"
    if not mesh_file.exists():
        raise FileNotFoundError(mesh_file)

    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(mesh_file))
    task.set_editor_property("destination_path", str(_parent_package(asset_path)))
    task.set_editor_property("destination_name", _leaf(asset_path))
    task.set_editor_property("automated", True)
    task.set_editor_property("save", True)
    task.set_editor_property("replace_existing", True)

    # OBJ import options come from the interchange pipeline in 5.6. The
    # default pipeline works for textured OBJs from scan apps; any sidecar
    # MTL in the same folder gets picked up automatically.
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    asset_tools.import_asset_tasks([task])

    imported = unreal.EditorAssetLibrary.load_asset(asset_path)
    if imported is None:
        raise RuntimeError(f"import failed, asset not present at {asset_path}")
    return imported


def create_metahuman_identity(asset_path: str,
                              scan_mesh: "unreal.StaticMesh") -> "unreal.Object":
    """Create a MetaHumanIdentity at asset_path with scan_mesh attached as
    the face neutral pose.

    API NOTE: concrete UCLASS names in 5.6 are `MetaHumanIdentity`,
    `MetaHumanIdentityFace`. The factory + promote-from-static-mesh
    convenience is in the shipped example; reproduce here.
    """
    parent = _parent_package(asset_path)
    name = _leaf(asset_path)

    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    factory = unreal.MetaHumanIdentityFactoryNew()  # API NOTE: verify class name
    identity = asset_tools.create_asset(
        asset_name=name,
        package_path=str(parent),
        asset_class=unreal.MetaHumanIdentity,  # API NOTE
        factory=factory,
    )
    if identity is None:
        raise RuntimeError(f"create_asset failed for {asset_path}")

    # Attach the scan mesh as the face part's neutral pose.
    # API NOTE: in Epic's example script, this is:
    #   face_part = identity.find_or_add_part_of_class(unreal.MetaHumanIdentityFace)
    #   face_part.set_neutral_pose_from_static_mesh(scan_mesh)
    face_part = identity.find_or_add_part_of_class(unreal.MetaHumanIdentityFace)
    face_part.set_neutral_pose_from_static_mesh(scan_mesh)

    unreal.EditorAssetLibrary.save_loaded_asset(identity)
    return identity


def run_tracking_and_conform(identity: "unreal.Object",
                             timeout_s: int = 300) -> None:
    """Fire the landmark tracking pipeline, wait, then conform the face."""
    # API NOTE: method names from the 5.6 forum reports.
    identity.start_frame_tracking_pipeline()

    deadline = time.time() + timeout_s
    while identity.is_frame_tracking_pipeline_processing():
        if time.time() > deadline:
            raise TimeoutError(f"tracking still running after {timeout_s}s")
        time.sleep(0.5)
        unreal.SystemLibrary.execute_console_command(None, "")  # keep UI responsive

    if identity.diagnostics_indicates_processing_issue():
        raise RuntimeError("MetaHumanIdentity diagnostics flagged the tracking result")

    face_part = identity.find_or_add_part_of_class(unreal.MetaHumanIdentityFace)
    face_part.conform()
    unreal.EditorAssetLibrary.save_loaded_asset(identity)


def create_and_autorig_character(asset_path: str,
                                 identity: "unreal.Object") -> "unreal.Object":
    """Create a MetaHumanCharacter seeded from identity and run the cloud
    auto-rig. Retries transient cloud failures.

    API NOTE: subsystem name `MetaHumanCharacterEditorSubsystem`. Functions
    `request_auto_rigging` and `request_texture_sources` take the character
    asset and a params struct.
    """
    parent = _parent_package(asset_path)
    name = _leaf(asset_path)

    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    factory = unreal.MetaHumanCharacterFactoryNew()  # API NOTE: verify class name
    character = asset_tools.create_asset(
        asset_name=name,
        package_path=str(parent),
        asset_class=unreal.MetaHumanCharacter,  # API NOTE
        factory=factory,
    )
    if character is None:
        raise RuntimeError(f"create_asset failed for {asset_path}")

    # Seed the character's face from the identity's conformed mesh.
    # API NOTE: the exact seeding call is plugin-version-specific.
    subsystem = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
    subsystem.seed_from_identity(character, identity)  # API NOTE: verify name

    # Auto-rig request with retry on transient errors.
    last_error: Exception | None = None
    commit_id = None
    for attempt, delay in enumerate((0,) + RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            result = subsystem.request_auto_rigging(character)  # API NOTE
            commit_id = getattr(result, "commit_id", None)
            if getattr(result, "success", True):
                break
            raise RuntimeError(getattr(result, "error_message", "auto-rig failed"))
        except Exception as e:
            last_error = e
            unreal.log_warning(
                f"[scan-to-mh] auto-rig attempt {attempt + 1} failed: {e}"
            )
    else:
        raise RuntimeError(f"auto-rig failed after retries: {last_error}")

    subsystem.request_texture_sources(character)  # API NOTE

    unreal.EditorAssetLibrary.save_loaded_asset(character)
    return character, commit_id


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

def _parent_package(asset_path: str) -> str:
    return asset_path.rsplit("/", 1)[0]


def _leaf(asset_path: str) -> str:
    return asset_path.rsplit("/", 1)[1]


def _sanitize(name: str) -> str:
    # UE asset names cannot contain '.', '-', spaces, etc. Keep letters,
    # digits, underscore.
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    # Parse --scan from either sys.argv or from the unreal Python command
    # line which appends args after the script path.
    p = argparse.ArgumentParser()
    p.add_argument("--scan", required=True)
    p.add_argument("--workspace", default=None,
                   help="repo root; defaults to script's great-grandparent")
    args = p.parse_args()

    script_dir = Path(__file__).resolve().parent
    workspace = Path(args.workspace).resolve() if args.workspace \
        else script_dir.parent.parent.parent
    scan_dir = workspace / "scans" / args.scan
    normalized_dir = scan_dir / "01-normalized"
    out_dir = scan_dir / "02-metahuman"

    if not normalized_dir.exists():
        print(f"run_scan: missing {normalized_dir}; run stage 01 first", file=sys.stderr)
        return 2

    cfg = load_config(workspace)
    ue_cfg = cfg.get("ue", {})
    content_subpath = cfg.get("content_subpath", "ScanCaptures").strip("/")

    scan_leaf = _sanitize(args.scan)
    asset_root = f"/Game/{content_subpath}/{args.scan}"
    scan_mesh_asset = f"{asset_root}/ScanMesh"
    identity_asset = f"{asset_root}/MHI_{scan_leaf}"
    character_asset = f"{asset_root}/MHC_{scan_leaf}"

    update_scan_manifest(scan_dir, "running")

    try:
        unreal.log(f"[scan-to-mh] importing {normalized_dir / 'mesh.obj'} -> {scan_mesh_asset}")
        mesh = import_scan_mesh(normalized_dir, scan_mesh_asset)

        unreal.log(f"[scan-to-mh] creating MetaHumanIdentity at {identity_asset}")
        identity = create_metahuman_identity(identity_asset, mesh)

        unreal.log("[scan-to-mh] running tracking + conform")
        run_tracking_and_conform(identity)

        unreal.log(f"[scan-to-mh] auto-rigging MetaHumanCharacter at {character_asset}")
        character, commit_id = create_and_autorig_character(character_asset, identity)

        out_dir.mkdir(parents=True, exist_ok=True)
        mh_manifest = {
            "scan_id": args.scan,
            "ue_project": str(ue_cfg.get("project", "")),
            "content_subpath": f"{content_subpath}/{args.scan}",
            "scan_mesh_asset": scan_mesh_asset,
            "identity_asset": identity_asset,
            "character_asset": character_asset,
            "auto_rig_commit": commit_id,
            "completed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        (out_dir / "metahuman_manifest.json").write_text(
            json.dumps(mh_manifest, indent=2) + "\n", encoding="utf-8"
        )

        update_scan_manifest(
            scan_dir, "done",
            outputs={
                "manifest": "02-metahuman/metahuman_manifest.json",
                "identity": identity_asset,
                "character": character_asset,
            },
        )
        unreal.log(f"[scan-to-mh] done. character at {character_asset}")
        return 0

    except Exception as e:
        err = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        update_scan_manifest(scan_dir, "failed", error=str(e))
        unreal.log_error(f"[scan-to-mh] FAILED: {err}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
