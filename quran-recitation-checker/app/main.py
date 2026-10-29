from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import profiles
from app.asr import registry
from app.config import CONFIG
from app.quran import page_loader
from app.quran.text import get_quran

logging.basicConfig(
    level=getattr(logging, CONFIG.LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger("app")


async def verify_api_key(
    api_key_query: str | None = Query(None, alias="api_key"),
    api_key_header: str | None = Header(None, alias="X-API-Key"),
):
    key = api_key_header or api_key_query
    if CONFIG.API_KEY and key != CONFIG.API_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API Key")
    return key


@asynccontextmanager
async def lifespan(app: FastAPI):
    profiles.load_overrides(CONFIG.PROFILES_PATH)
    get_quran()
    page_loader.load_page_map()
    logger.info("Qur'an text loaded; loading ASR model %s in the background ...",
                CONFIG.WHISPER_MODEL_DIR or CONFIG.WHISPER_MODEL_SIZE)
    registry.preload_in_background()
    yield


app = FastAPI(title="Qur'an Recitation Checker", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(CONFIG.FRONTEND_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.ws_router import router as ws_router  # noqa: E402

app.include_router(ws_router)


@app.get("/ayah/{surah}/{ayah}", dependencies=[Depends(verify_api_key)])
def get_ayah_tokens(surah: int, ayah: int):
    q = get_quran()
    if not q.exists(surah, ayah):
        return JSONResponse(status_code=404, content={
            "error": "not_found", "detail": f"{surah}:{ayah} not found", "ref_tokens": []})
    return {"ref_tokens": q.display_tokens(surah, ayah),
            "imlaei_tokens": [w.imlaei for w in q.words(surah, ayah)]}


@app.get("/meta/surah/{surah}", dependencies=[Depends(verify_api_key)])
def get_surah_meta(surah: int):
    try:
        return {"surah": surah, "ayah_count": get_quran().ayah_count(surah)}
    except KeyError:
        return JSONResponse(status_code=404, content={"error": "not_found", "detail": f"Surah {surah} not found"})


@app.get("/meta/surahs", dependencies=[Depends(verify_api_key)])
def list_surahs():
    path = Path(CONFIG.METADATA_PATH)
    if not path.exists():
        return JSONResponse(status_code=404, content={"error": "not_found", "detail": f"{path} not found"})
    return {"surahs": json.loads(path.read_text(encoding="utf-8"))}


@app.get("/meta/page/{page_id}", dependencies=[Depends(verify_api_key)])
def get_page_details(page_id: int):
    try:
        return page_loader.get_page_content(page_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/meta/lookup/page", dependencies=[Depends(verify_api_key)])
def lookup_page_for_verse(surah: int, ayah: int):
    return {"page": page_loader.find_page_for_ayah(surah, ayah)}


@app.get("/api/profiles", dependencies=[Depends(verify_api_key)])
def list_profiles():
    return {name: asdict(p) for name, p in profiles.all_profiles().items()}


@app.post("/api/check", dependencies=[Depends(verify_api_key)])
async def check_recording(
    file: UploadFile = File(..., description="Recording (wav, mp3, m4a, webm, ...)"),
    surah: int = Form(...),
    ayah: int = Form(...),
    profile: str = Form("medium"),
):
    """Check a whole recording (same pipeline as live). Returns per-verse verdicts."""
    from app.offline import check_audio, load_audio

    if not get_quran().exists(surah, ayah):
        raise HTTPException(status_code=404, detail=f"{surah}:{ayah} not found")
    suffix = Path(file.filename or "audio").suffix or ".bin"
    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp.flush()
        loop = asyncio.get_running_loop()
        audio = await loop.run_in_executor(None, load_audio, tmp.name)
    backend = await loop.run_in_executor(None, registry.get_backend)
    return await loop.run_in_executor(
        registry.EXECUTOR, lambda: check_audio(audio, surah, ayah, profile, backend))
