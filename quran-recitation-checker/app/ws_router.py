"""
WebSocket /ws/recite and the session/health endpoints.

Protocol (backwards compatible with M2)
  connect   /ws/recite?surah=2&ayah=1&profile=medium&session_id=<uuid>&api_key=<key>
  client -> binary frames: PCM 16-bit little-endian, mono, 16 kHz
  client -> text: "surah:2,ayah:5"          jump to a verse (M2 format), or JSON:
                  {"type":"goto","surah":2,"ayah":5}
                  {"type":"profile","profile":"strict"}
                  {"type":"stop"}             flush, send final results, keep socket open
  server -> {"status":"loading"} while the model loads, then {"status":"ready"}
  server -> {"type":"update", ...} after every decode (see README for fields)
  server -> {"type":"final",  ...} after "stop"
  server -> {"error":"..."} on problems
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.asr import registry
from app.config import CONFIG
from app.recitation import RecitationSession
from app.session_store import get_session

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
def health_check():
    asr = registry.status()
    return {"status": "ok" if not asr["error"] else "degraded",
            "engine_ready": asr["ready"], "engine_type": asr["engine"], "asr": asr}


@router.get("/api/session/{session_id}/summary")
def get_session_summary(session_id: str):
    session = get_session(session_id)
    if not session:
        return {"error": "Session not found"}
    return session.to_dict()


def _parse_control(text: str) -> dict:
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)
    kv = dict(part.split(":", 1) for part in text.split(",") if ":" in part)  # M2 "surah:2,ayah:3"
    if "surah" in kv and "ayah" in kv:
        return {"type": "goto", "surah": int(kv["surah"]), "ayah": int(kv["ayah"])}
    if text in ("stop", "finish"):
        return {"type": "stop"}
    raise ValueError(f"unknown control message: {text!r}")


@router.websocket("/ws/recite")
async def ws_recite(
    websocket: WebSocket,
    surah: int = Query(...),
    ayah: int = Query(...),
    api_key: str | None = Query(None),
    profile: str = Query("medium"),
    session_id: str | None = Query(None),
):
    if CONFIG.API_KEY and api_key != CONFIG.API_KEY:
        logger.warning("WS connection rejected: invalid API key")
        await websocket.close(code=1008, reason="Invalid API Key")
        return
    await websocket.accept()
    loop = asyncio.get_running_loop()

    async def send(obj: dict) -> None:
        if websocket.client_state == WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await websocket.send_json(obj)

    if not registry.status()["ready"]:
        await send({"status": "loading"})
    try:
        backend = await loop.run_in_executor(None, registry.get_backend)
    except Exception as e:
        await send({"error": f"ASR model failed to load: {e}. See server log; deleting the "
                             f"models/ folder forces a fresh download."})
        await websocket.close(code=1011)
        return

    try:
        rs = RecitationSession(backend, surah, ayah, profile, session_id)
    except KeyError as e:
        await send({"error": str(e)})
        await websocket.close(code=1008)
        return

    await send({"status": "ready"})
    await send(await loop.run_in_executor(registry.EXECUTOR, rs.snapshot))
    logger.info("WS connected: %s:%s profile=%s session=%s", surah, ayah, profile, session_id)

    decode_lock = asyncio.Lock()  # one decode at a time per connection
    step_s = max(0.2, CONFIG.STREAM_STEP_MS / 1000.0)
    stopped = False

    async def decoder() -> None:
        while not stopped:
            await asyncio.sleep(0.05)
            if rs.pending_seconds() < step_s:
                continue
            async with decode_lock:
                try:
                    payload = await loop.run_in_executor(registry.EXECUTOR, rs.step)
                except Exception:
                    logger.exception("decode failed")
                    continue
            await send(payload)

    task = asyncio.create_task(decoder())
    try:
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes"):
                rs.add_pcm16(msg["bytes"])
                continue
            if not msg.get("text"):
                continue
            try:
                cmd = _parse_control(msg["text"])
            except Exception as e:
                await send({"error": f"bad control message: {e}"})
                continue
            kind = cmd.get("type")
            if kind == "stop":
                stopped = True
                task.cancel()
                async with decode_lock:
                    final = await loop.run_in_executor(registry.EXECUTOR, rs.finish)
                await send(final)
            elif kind == "goto":
                async with decode_lock:
                    payload = await loop.run_in_executor(
                        registry.EXECUTOR, rs.goto, int(cmd["surah"]), int(cmd["ayah"]))
                if payload is not None:
                    await send(payload)
            elif kind == "profile":
                rs.set_profile(str(cmd.get("profile", "medium")))
            else:
                await send({"error": f"unknown control type {kind!r}"})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("WS loop error")
        await send({"error": str(e)})
    finally:
        task.cancel()
        if not stopped:  # client vanished: still save what was recited
            with contextlib.suppress(Exception):
                async with decode_lock:
                    await loop.run_in_executor(registry.EXECUTOR, rs.finish)
        with contextlib.suppress(Exception):
            await websocket.close()
        logger.info("WS closed (session=%s)", session_id)
