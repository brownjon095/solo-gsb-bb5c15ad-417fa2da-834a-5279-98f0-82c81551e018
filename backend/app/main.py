"""FastAPI entry point for the multilingual font fallback workbench."""
from __future__ import annotations

import json
import pathlib
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .manifest import ManifestError, parse_manifest
from .resolver import diagnose
from .segmentation import segment
from .unicode_blocks import all_block_names, block_range

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT.parent / "data"
STATIC_DIR = ROOT.parent / "frontend" / "dist"
SAMPLE_PATH = DATA_DIR / "sample-coverage.json"

app = FastAPI(title="Font Fallback Workbench", version="1.0.0")


class DiagnoseRequest(BaseModel):
    text: str = Field("", description="Mixed-language text to diagnose")
    manifest: dict[str, Any] | None = None
    manifestText: str | None = Field(None, description="Raw manifest JSON from the editor")
    mode: Literal["cluster", "codepoint"] = "cluster"


class ManifestRequest(BaseModel):
    manifestText: str = "{}"


def _load_manifest_from_request(req: DiagnoseRequest):
    if req.manifest is not None:
        data = req.manifest
    elif req.manifestText:
        try:
            data = json.loads(req.manifestText)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=400,
                detail={"error": "invalid_json",
                        "message": f"清单 JSON 解析失败：第 {e.lineno} 行第 {e.colno} 列 — {e.msg}"},
            )
    else:
        data = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    try:
        return parse_manifest(data)
    except ManifestError as e:
        raise HTTPException(status_code=422,
                            detail={"error": "invalid_manifest", "message": str(e)})


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/sample-manifest")
def sample_manifest() -> JSONResponse:
    return JSONResponse(json.loads(SAMPLE_PATH.read_text(encoding="utf-8")))


@app.get("/api/blocks")
def blocks() -> dict:
    names = all_block_names()
    return {"blocks": [{"name": n, "range": block_range(n)} for n in names]}


@app.post("/api/validate-manifest")
def validate_manifest(req: ManifestRequest) -> dict:
    try:
        data = json.loads(req.manifestText)
    except json.JSONDecodeError as e:
        return {"valid": False,
                "error": {"kind": "invalid_json",
                          "message": f"JSON 解析失败：第 {e.lineno} 行第 {e.colno} 列 — {e.msg}",
                          "line": e.lineno, "column": e.colno}}
    try:
        m = parse_manifest(data)
    except ManifestError as e:
        return {"valid": False, "error": {"kind": "invalid_manifest", "message": str(e)}}
    order, issues = m.effective_order()
    return {
        "valid": True,
        "warnings": m.warnings,
        "fontCount": len(m.fonts),
        "order": m.order,
        "effectiveOrder": order,
        "issues": issues + m.detect_order_duplicates(),
        "fonts": [
            {"name": n, "coverageSize": f.coverage_size(),
             "intervalCount": len(f.intervals), "aliasFor": f.alias_for}
            for n, f in m.fonts.items()
        ],
    }


@app.post("/api/diagnose")
def diagnose_text(req: DiagnoseRequest) -> dict:
    manifest = _load_manifest_from_request(req)
    clusters = segment(req.text)
    result = diagnose(req.text, clusters, manifest, mode=req.mode)
    return {"text": req.text, **result}


# ---- static frontend (served when the built bundle exists) ------------------
if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        target = STATIC_DIR / full_path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(STATIC_DIR / "index.html")
