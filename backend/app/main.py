"""FastAPI HTTP 层：API 路由 + 前端静态资源托管。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .coverage import parse_manifest
from .samples import SAMPLE_MANIFEST, SAMPLE_TEXT
from .service import run_diagnose

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="多语言字体回退诊断台", version="1.0.0")


class DiagnoseRequest(BaseModel):
    text: str
    manifest: dict
    priority: list[str] | None = None


class ValidateRequest(BaseModel):
    manifest: dict


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/defaults")
def defaults() -> dict:
    return {
        "sampleText": SAMPLE_TEXT,
        "manifest": SAMPLE_MANIFEST,
        "priority": SAMPLE_MANIFEST["priority"],
    }


@app.post("/api/diagnose")
def diagnose(req: DiagnoseRequest) -> dict:
    return run_diagnose(req.text, req.manifest, req.priority)


@app.post("/api/manifest/validate")
def validate_manifest(req: ValidateRequest) -> dict:
    fonts, errors, priority = parse_manifest(req.manifest)
    return {
        "ok": not errors,
        "errors": errors,
        "fontCount": len(fonts),
        "codepointCount": sum(f.codepoint_count for f in fonts.values()),
        "priority": priority,
    }


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    """托管前端构建产物；未命中文件时回退到 index.html（SPA）。"""
    if STATIC_DIR.is_dir():
        candidate = (STATIC_DIR / full_path).resolve()
        if full_path and candidate.is_file() and STATIC_DIR in candidate.parents:
            return FileResponse(candidate)
        index = STATIC_DIR / "index.html"
        if index.is_file():
            return FileResponse(index)
    return JSONResponse(
        {"detail": "前端尚未构建：请先构建 frontend 或仅使用 /api 接口。"},
        status_code=404,
    )
