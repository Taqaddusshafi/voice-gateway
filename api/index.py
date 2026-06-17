"""Vercel serverless entry — lightweight FastAPI with no database.

Proxies TTS/STT requests to the hosted engines and serves health checks.
"""

import os
import httpx
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, status
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware

TTS_ENGINE_URL = os.environ.get("TTS_ENGINE_URL", "http://185.14.252.20:8000")
TTS_ENGINE_PATH = os.environ.get("TTS_ENGINE_PATH", "/v1/tts")
STT_ENGINE_URL = os.environ.get("STT_ENGINE_URL", "http://185.14.252.20:8002")
STT_ENGINE_PATH = os.environ.get("STT_ENGINE_PATH", "/v1/stt")
ENGINE_TIMEOUT = float(os.environ.get("ENGINE_TIMEOUT_SECONDS", "60"))

app = FastAPI(title="Voice Gateway Demo", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/engine-health")
async def engine_health():
    """Connectivity check against both engines."""
    results = {}
    for label, url in [("tts", TTS_ENGINE_URL), ("stt", STT_ENGINE_URL)]:
        if not url:
            results[label] = {"status": "not_configured"}
            continue
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, timeout=5)
                results[label] = {"status": "ok", "http": r.status_code}
        except Exception as exc:
            results[label] = {"status": "unreachable", "error": str(exc)}
    return results


@app.post("/api/tts")
async def demo_tts(
    text: str = Form(...),
    language: str = Form(default="en"),
    voice: str = Form(default="en-US-female-1"),
):
    """Proxy TTS request to the engine and return raw audio bytes."""
    url = f"{TTS_ENGINE_URL.rstrip('/')}{TTS_ENGINE_PATH}"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json={"text": text, "language": language, "voice": voice},
                timeout=ENGINE_TIMEOUT,
            )
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "audio/wav")
            return Response(content=resp.content, media_type=content_type)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"TTS engine error: {exc.response.text[:500]}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"TTS engine unreachable: {exc}",
        )


@app.post("/api/stt")
async def demo_stt(
    file: UploadFile = File(...),
    language: str = Form(default=None),
):
    """Proxy STT request to the engine and return the transcript."""
    if not STT_ENGINE_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="STT engine URL is not configured",
        )
    url = f"{STT_ENGINE_URL.rstrip('/')}{STT_ENGINE_PATH}"
    data = await file.read()
    filename = file.filename or "audio.wav"
    # Strip codec params: 'audio/webm;codecs=opus' → 'audio/webm'
    raw_ct = file.content_type or "audio/wav"
    content_type = raw_ct.split(";")[0].strip()
    form_data = {}
    if language:
        form_data["language"] = language

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                files={"file": (filename, data, content_type)},
                data=form_data,
                timeout=ENGINE_TIMEOUT,
            )
            resp.raise_for_status()
            ct = resp.headers.get("content-type", "")
            if "application/json" in ct:
                return resp.json()
            return {"text": resp.text.strip()}
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"STT engine error: {exc.response.text[:500]}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"STT engine unreachable: {exc}",
        )
