"""Stage 01 normalizer.

Accept an arbitrary upload at scans/<id>/source/ and produce a canonical
mesh + texture pair at scans/<id>/01-normalized/. See the stage's
CONTEXT.md for the full contract.

Deterministic Python; no LLM in the loop.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

try:
    import yaml  # PyYAML
except ImportError as e:
    print("normalize: PyYAML required. pip install pyyaml", file=sys.stderr)
    raise

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".tga", ".tif", ".tiff"}


# ---------------------------------------------------------------------------
# Unzip helpers
# ---------------------------------------------------------------------------

def extract_source(source_dir: Path, tmp: Path) -> Path:
    """Materialise the upload into a flat working directory.

    - If source_dir contains exactly one .zip, extract it into tmp.
    - If the extraction yields a single nested .zip (Sketchfab pattern:
      source/Person.zip.zip), extract that one level too.
    - Otherwise copy the raw source files into tmp.
    """
    files = [p for p in source_dir.iterdir() if p.is_file()]
    zips = [p for p in files if p.suffix.lower() == ".zip"]

    if len(files) == 1 and len(zips) == 1:
        with zipfile.ZipFile(zips[0]) as z:
            z.extractall(tmp)
        nested = [p for p in tmp.rglob("*.zip")]
        if len(nested) == 1:
            inner_tmp = tmp / "_nested"
            inner_tmp.mkdir()
            with zipfile.ZipFile(nested[0]) as z:
                z.extractall(inner_tmp)
            # Flatten: whichever dir has more mesh-like files wins.
            return inner_tmp if _count_meshes(inner_tmp) >= _count_meshes(tmp) else tmp
        return tmp

    # Copy source files as-is.
    for p in source_dir.rglob("*"):
        if p.is_file():
            rel = p.relative_to(source_dir)
            dest = tmp / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
    return tmp


def _count_meshes(root: Path) -> int:
    n = 0
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".obj", ".fbx", ".ply", ".glb", ".usdz"}:
            n += 1
    return n


# ---------------------------------------------------------------------------
# Pick primary mesh and texture
# ---------------------------------------------------------------------------

def pick_mesh(root: Path, accept_formats: list[str]) -> Path:
    accepted = {"." + fmt.lower() for fmt in accept_formats}
    candidates = [
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in accepted
    ]
    if not candidates:
        raise SystemExit(
            f"normalize: no mesh in accept_formats={accept_formats} under {root}"
        )
    # Largest by bytes wins.
    candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
    return candidates[0]


def pick_texture(root: Path, mesh: Path) -> Path | None:
    """Priority order:
    1. A file referenced by the mesh sidecar (`.mtl` next to the OBJ).
    2. Largest image file by bytes.
    """
    # OBJ: read sidecar .mtl for map_Kd entries.
    if mesh.suffix.lower() == ".obj":
        mtl_paths = [mesh.with_suffix(".mtl"), mesh.with_suffix(".obj.mtl")]
        for mtl in mtl_paths:
            if mtl.exists():
                refs = _mtl_textures(mtl)
                for ref in refs:
                    candidate = (mtl.parent / ref).resolve()
                    if candidate.exists():
                        return candidate
                # Fallback: any image in the same directory matching the
                # reference's basename.
                for ref in refs:
                    name = Path(ref).name
                    for p in root.rglob(name):
                        if p.is_file():
                            return p
    # Fallback: largest image in the tree.
    imgs = [
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]
    if not imgs:
        return None
    imgs.sort(key=lambda p: p.stat().st_size, reverse=True)
    return imgs[0]


def _mtl_textures(mtl: Path) -> list[str]:
    refs: list[str] = []
    for line in mtl.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = re.match(r"\s*(map_Kd|map_Ka|map_Ks|map_Bump|bump)\s+(.+?)\s*$", line)
        if m:
            refs.append(m.group(2).strip())
    return refs


# ---------------------------------------------------------------------------
# Mesh stats
# ---------------------------------------------------------------------------

def obj_triangle_count(obj: Path) -> int:
    """Lightweight triangle count from an OBJ. Counts f-lines, assuming
    mostly triangulated scans (each f-line = 1 triangle; n-gons undercount
    slightly but this is a sanity number, not a spec)."""
    n = 0
    with obj.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("f "):
                n += 1
    return n


def image_dimensions(img: Path) -> tuple[int, int] | None:
    """Pull (width, height) out of PNG/JPEG without Pillow."""
    try:
        with img.open("rb") as f:
            header = f.read(32)
        ext = img.suffix.lower()
        if ext == ".png" and header[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", header[16:24])
            return w, h
        if ext in (".jpg", ".jpeg"):
            return _jpeg_dimensions(img)
    except Exception:
        return None
    return None


def _jpeg_dimensions(img: Path) -> tuple[int, int] | None:
    with img.open("rb") as f:
        if f.read(2) != b"\xff\xd8":
            return None
        while True:
            marker = f.read(1)
            if not marker:
                return None
            while marker == b"\xff":
                marker = f.read(1)
            b = marker[0]
            # SOF markers
            if b in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                     0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                f.read(3)  # length (2) + precision (1)
                h, w = struct.unpack(">HH", f.read(4))
                return w, h
            # skip segment
            seg_len_bytes = f.read(2)
            if len(seg_len_bytes) < 2:
                return None
            seg_len = struct.unpack(">H", seg_len_bytes)[0]
            f.read(seg_len - 2)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# MTL rewrite for OBJ
# ---------------------------------------------------------------------------

def rewrite_mtl_for_local_texture(mtl_out: Path, texture_basename: str) -> None:
    """Rewrite every map_* line to point at texture_basename. Preserves
    other lines (Ka, Kd, Ks, etc.). If no map_Kd existed, appends one to
    the first newmtl block."""
    src = mtl_out.read_text(encoding="utf-8", errors="ignore")
    out: list[str] = []
    saw_map_kd = False
    for line in src.splitlines():
        m = re.match(r"(\s*)(map_Kd|map_Ka|map_Ks|map_Bump|bump)\s+.+$", line)
        if m:
            if m.group(2) == "map_Kd":
                saw_map_kd = True
            out.append(f"{m.group(1)}{m.group(2)} {texture_basename}")
        else:
            out.append(line)
    if not saw_map_kd and out:
        # Append to the first newmtl block.
        for i, line in enumerate(out):
            if line.startswith("newmtl"):
                out.insert(i + 1, f"map_Kd {texture_basename}")
                break
        else:
            out.append(f"newmtl scan_material\nmap_Kd {texture_basename}")
    mtl_out.write_text("\n".join(out) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Top-level manifest update
# ---------------------------------------------------------------------------

def update_scan_manifest(scan_dir: Path, status: str, outputs: dict | None = None,
                         error: str | None = None) -> None:
    manifest_path = scan_dir / "manifest.json"
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    if manifest_path.exists():
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        m = {
            "id": scan_dir.name,
            "created": now,
            "stages": {},
        }
    stage = m["stages"].setdefault("01-normalize-scan", {"status": "pending"})
    if status == "running" and "started" not in stage:
        stage["started"] = now
    stage["status"] = status
    if status in ("done", "failed"):
        stage["finished"] = now
    if outputs is not None:
        stage["outputs"] = outputs
    if error is not None:
        stage["error"] = error
    manifest_path.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Stage 01 normalize-scan")
    p.add_argument("--scan", required=True, help="scan id (scans/<id>/)")
    p.add_argument("--workspace", default=None,
                   help="repo root; defaults to script's great-grandparent")
    args = p.parse_args()

    script_dir = Path(__file__).resolve().parent
    workspace = Path(args.workspace).resolve() if args.workspace \
        else script_dir.parent.parent.parent
    scan_dir = workspace / "scans" / args.scan
    source_dir = scan_dir / "source"
    out_dir = scan_dir / "01-normalized"

    if not source_dir.exists() or not any(source_dir.iterdir()):
        print(f"normalize: no upload at {source_dir}", file=sys.stderr)
        return 2

    cfg_path = workspace / "_config" / "pipeline.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    norm = cfg.get("normalize", {})
    accept = norm.get("accept_formats", ["obj"])
    max_tris = int(norm.get("max_tris", 200000))
    max_tex = int(norm.get("max_texture_px", 4096))

    update_scan_manifest(scan_dir, "running")

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        for p in out_dir.iterdir():
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                shutil.rmtree(p)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            staging = extract_source(source_dir, tmp_path)
            mesh = pick_mesh(staging, accept)
            texture = pick_texture(staging, mesh)
            if texture is None:
                raise RuntimeError("no texture image found alongside the mesh")

            mesh_out = out_dir / f"mesh{mesh.suffix.lower()}"
            tex_out = out_dir / f"texture{texture.suffix.lower()}"
            shutil.copy2(mesh, mesh_out)
            shutil.copy2(texture, tex_out)

            # Copy sidecar MTL for OBJ; rewrite map_Kd to local texture name.
            if mesh.suffix.lower() == ".obj":
                sidecar_candidates = [
                    mesh.with_suffix(".mtl"),
                    mesh.with_suffix(".obj.mtl"),
                ]
                mtl_src = next((p for p in sidecar_candidates if p.exists()), None)
                mtl_out = out_dir / "mesh.mtl"
                if mtl_src:
                    shutil.copy2(mtl_src, mtl_out)
                else:
                    mtl_out.write_text(
                        "newmtl scan_material\n"
                        f"map_Kd {tex_out.name}\n", encoding="utf-8"
                    )
                rewrite_mtl_for_local_texture(mtl_out, tex_out.name)
                # Make sure the OBJ's mtllib points at mesh.mtl.
                _rewrite_obj_mtllib(mesh_out, "mesh.mtl")

            tri_count = obj_triangle_count(mesh_out) if mesh_out.suffix == ".obj" else -1
            dims = image_dimensions(tex_out)
            oversized = tri_count > max_tris if tri_count >= 0 else False
            if dims and (dims[0] > max_tex or dims[1] > max_tex):
                oversized = True

            scan_manifest = {
                "scan_id": args.scan,
                "source_upload": _first_source_name(source_dir),
                "primary_mesh": {
                    "path": mesh_out.name,
                    "format": mesh_out.suffix.lstrip(".").lower(),
                    "triangles": tri_count,
                    "sha256": sha256(mesh_out),
                },
                "primary_texture": {
                    "path": tex_out.name,
                    "format": tex_out.suffix.lstrip(".").lower(),
                    "width": dims[0] if dims else None,
                    "height": dims[1] if dims else None,
                    "sha256": sha256(tex_out),
                },
                "oversized": oversized,
                "notes": [],
            }
            if oversized:
                scan_manifest["notes"].append(
                    f"above limits: tris={tri_count} (max {max_tris}), "
                    f"tex={dims} (max {max_tex})"
                )
            (out_dir / "scan_manifest.json").write_text(
                json.dumps(scan_manifest, indent=2) + "\n", encoding="utf-8"
            )

            update_scan_manifest(
                scan_dir, "done",
                outputs={
                    "mesh": f"01-normalized/{mesh_out.name}",
                    "texture": f"01-normalized/{tex_out.name}",
                    "manifest": "01-normalized/scan_manifest.json",
                },
            )
            print(
                f"normalize: wrote {mesh_out.name} ({tri_count} tris) "
                f"+ {tex_out.name} ({dims if dims else 'unknown dims'}) "
                f"to {out_dir}{' (OVERSIZED)' if oversized else ''}"
            )
            return 0
    except Exception as e:
        update_scan_manifest(scan_dir, "failed", error=str(e))
        print(f"normalize: FAILED: {e}", file=sys.stderr)
        return 1


def _rewrite_obj_mtllib(obj_path: Path, mtl_name: str) -> None:
    src = obj_path.read_text(encoding="utf-8", errors="ignore")
    lines = src.splitlines()
    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith("mtllib"):
            lines[i] = f"mtllib {mtl_name}"
            replaced = True
            break
    if not replaced:
        lines.insert(0, f"mtllib {mtl_name}")
    obj_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _first_source_name(source_dir: Path) -> str:
    for p in source_dir.iterdir():
        if p.is_file():
            return p.name
    return "(empty)"


if __name__ == "__main__":
    raise SystemExit(main())
