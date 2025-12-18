# wrapper_multimodal_tts.py — Agora-compatible SSE streaming + STT + TTS (fixed audio output)
import os
import json
import uuid
import asyncio
import base64
import re
from typing import AsyncGenerator, List, Optional, Union, Dict, Any, Literal
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
import httpx
from pydantic import BaseModel, Field

load_dotenv()

# Config (edit .env in repo root)
LIGHTRAG_URL = os.getenv("LIGHTRAG_URL", "http://localhost:9621/query")
LIGHTRAG_STREAM_URL = os.getenv("LIGHTRAG_STREAM_URL", LIGHTRAG_URL.rstrip("/") + "/stream")
WRAPPER_API_KEY = os.getenv("WRAPPER_API_KEY", "")     # optional wrapper auth
LIGHTRAG_API_KEY = os.getenv("LIGHTRAG_API_KEY", "")   # optional LightRAG auth
WRAPPER_PORT = int(os.getenv("WRAPPER_PORT", "8080"))
HTTP_TIMEOUT = int(os.getenv("WRAPPER_TIMEOUT", "60"))

app = FastAPI(title="Agora-compatible Custom LLM Wrapper (multimodal + fixed TTS)")

# Clean text for TTS: remove markdown, fix hyphenation, collapse spaces
def clean_text_for_tts(text: str) -> str:
    if not text:
        return ""

    # 1. Remove Markdown symbols: **, *, #, -, >, ``` , _, etc.
    text = re.sub(r"[*#`_>\[\]\(\)\-]+", " ", text)

    # 2. Remove LaTeX-style characters: ^, \, { }, $
    text = re.sub(r"[\\\^\{\}\$]", " ", text)

    # 3. Remove markdown headings like ###, ##, #####
    text = re.sub(r"#{1,6}", " ", text)

    # 4. Remove bullet markers like "- " or "* "
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)

    # 5. Remove leftover slashes or parentheses fragments
    text = re.sub(r"[\/]+", " ", text)

    # 6. Collapse duplicate spaces
    text = re.sub(r"\s+", " ", text).strip()

    return text

# ----------------------------
# Pydantic models for multimodal content
# ----------------------------
class TextContent(BaseModel):
    type: Literal["text"] = "text"
    text: str

class InputAudioContent(BaseModel):
    type: Literal["input_audio"] = "input_audio"
    input_audio: Dict[str, Any]  # e.g. {"data": "<base64>", "format": "pcm16"}

ContentItem = Union[TextContent, InputAudioContent]

class ChatMessage(BaseModel):
    role: str
    # Accept either simple string or list of content items
    content: Union[str, List[Dict[str, Any]]]

class ChatReq(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage] = []
    stream: Optional[bool] = True
    modalities: Optional[List[str]] = None  # e.g. ["text","audio"]
    audio: Optional[Dict[str, Any]] = None  # e.g. {"format":"pcm16"}

# ----------------------------
# Helpers
# ----------------------------
def sse_event(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

def chunk_text_by_words(text: str, words_per_chunk: int = 6):
    if not text:
        return []
    words = text.split()
    for i in range(0, len(words), words_per_chunk):
        yield " ".join(words[i:i+words_per_chunk])

async def call_lightrag_query(payload, headers):
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        return await client.post(LIGHTRAG_URL, json=payload, headers=headers, timeout=HTTP_TIMEOUT)

# ----------------------------
# Mock STT / TTS — replace with real implementations
# ----------------------------
def stt_decode_audio(base64_b64: str, fmt: str = "pcm16") -> str:
    """
    Mock STT: decode base64 audio and return a simple transcription.
    Replace with actual STT call.
    """
    try:
        audio_bytes = base64.b64decode(base64_b64)
        snippet = audio_bytes[:16].hex()
        return f"[transcription:{snippet}]"
    except Exception:
        return "[untranscribable audio]"

def tts_synthesize_bytes(text: str, fmt: str = "pcm16") -> bytes:
    """
    Mock TTS: convert text to "audio" bytes (here we just encode text).
    Replace with a real TTS engine producing PCM/opus/wav bytes.
    """
    # WARNING: placeholder. Use a real TTS producing raw audio bytes.
    return text.encode("utf-8")

def make_audio_base64_chunks(audio_bytes: bytes, chunk_size: int = 1024):
    for i in range(0, len(audio_bytes), chunk_size):
        yield base64.b64encode(audio_bytes[i:i+chunk_size]).decode("ascii")

# ----------------------------
# Core endpoint (fixed TTS behavior)
# ----------------------------
@app.post("/chat/completions")
async def chat_completions(req: ChatReq, x_api_key: Optional[str] = Header(None)):
    # AUTH DISABLED FOR AGORA
    # if WRAPPER_API_KEY and x_api_key != WRAPPER_API_KEY:
    #     raise HTTPException(status_code=401, detail="Invalid wrapper API key")

    # Normalize modalities
    modalities = req.modalities or ["text"]
    want_audio_output = "audio" in modalities
    want_text_output = "text" in modalities or modalities == ["text"]

    # Extract last user content — supports structured messages or plain string
    def extract_last_user(messages: List[ChatMessage]) -> Optional[Union[str, List[Dict[str, Any]]]]:
        for m in reversed(messages):
            if m.role.lower() == "user":
                return m.content
        return None

    last_user = extract_last_user(req.messages)
    if not last_user:
        raise HTTPException(status_code=400, detail="No user message found")

    # If user content is structured and contains input_audio -> run STT and replace with text
    final_text_input = None
    if isinstance(last_user, str):
        final_text_input = last_user
    else:
        # last_user is a list of dicts
        collected_texts: List[str] = []
        for item in last_user:
            if isinstance(item, dict):
                typ = item.get("type")
                if typ == "text":
                    t = item.get("text", "")
                    if t:
                        collected_texts.append(t)
                elif typ == "input_audio":
                    audio_info = item.get("input_audio", {})
                    data_b64 = audio_info.get("data")
                    fmt = audio_info.get("format", "pcm16")
                    if data_b64:
                        transcript = stt_decode_audio(data_b64, fmt)
                        collected_texts.append(transcript)
            else:
                # unexpected structure: treat as string
                try:
                    collected_texts.append(str(item))
                except Exception:
                    pass
        final_text_input = " ".join(collected_texts).strip()

    if not final_text_input:
        raise HTTPException(status_code=400, detail="No usable user text after STT")

    # Prepare payload for LightRAG / LLM backend
    payload = {"query": final_text_input, "mode": "mix", "include_references": False}
    headers = {"Content-Type": "application/json"}
    if LIGHTRAG_API_KEY:
        headers["X-API-Key"] = LIGHTRAG_API_KEY

    # ----------------------
    # Non-streaming: strict OpenAI ChatCompletion JSON (no extra fields)
    # ----------------------
    if not req.stream:
        try:
            r = await call_lightrag_query(payload, headers)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"LightRAG request failed: {e}")

        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"LightRAG error: {r.status_code} {r.text}")

        jr = r.json()
        text_answer = jr.get("response") or jr.get("answer") or jr.get("result") or json.dumps(jr)

        out = {
            "id": "custom-lm-wrapper-1",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text_answer},
                    "finish_reason": "stop"
                }
            ]
        }
        return JSONResponse(out)

    # ----------------------
    # Streaming mode: return SSE (support text chunks and audio chunks)
    # ----------------------
    stream_id = str(uuid.uuid4())

    async def stream_generator() -> AsyncGenerator[str, None]:
        buffer = []   # NEW: buffer for text chunks

        # We'll accumulate final_text for TTS if needed
        aggregated_text_parts: List[str] = []

        # 1) Try to proxy LightRAG streaming endpoint if available
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", LIGHTRAG_STREAM_URL, json=payload, headers=headers) as resp:
                    if resp.status_code == 200:
                        # Helper: yield text chunks (only when want_text_output)
                        def yield_text_chunks_from(text: str):
                            for piece in chunk_text_by_words(text, words_per_chunk=6):
                                out = {
                                    "id": stream_id,
                                    "object": "chat.completion.chunk",
                                    "choices": [{"delta": {"content": piece}}]
                                }
                                yield sse_event(out)

                        async for raw_line in resp.aiter_lines():
                            if raw_line is None:
                                continue
                            line = raw_line.strip()
                            if not line:
                                continue

                            parsed = None
                            try:
                                parsed = json.loads(line)
                            except Exception:
                                parsed = None

                            # If parsed is a dict, handle specifically
                            if isinstance(parsed, dict):
                                # If it's an Agora-style chunk
                                if parsed.get("object") == "chat.completion.chunk":
                                    # If it already has audio delta, forward it regardless
                                    choices = parsed.get("choices", [])
                                    delta = choices[0].get("delta", {}) if choices else {}
                                    if delta.get("audio"):
                                        # forward audio chunk as-is but ensure id
                                        parsed["id"] = stream_id
                                        yield sse_event(parsed)
                                        continue

                                    # If delta has content (text)
                                    if isinstance(delta.get("content"), str):
                                        text_piece = delta.get("content")
                                        aggregated_text_parts.append(text_piece)

                                        # ---- NEW: BUFFER TEXT FOR SMOOTH TTS ----
                                        buffer.append(text_piece)

                                        # Flush buffer when:
                                        # 1) sentence end detected, or
                                        # 2) buffer gets too long
                                        if any(p in text_piece for p in [".", "!", "?"]) or len(" ".join(buffer).split()) >= 12:

                                            combined = " ".join(buffer)
                                            buffer = []  # reset buffer

                                            if want_text_output and not want_audio_output:
                                                parsed["id"] = stream_id
                                                parsed["choices"][0]["delta"]["content"] = combined
                                                yield sse_event(parsed)

                                        continue


                                    # delta.content could be object — attempt to extract textual field
                                    dc = delta.get("content")
                                    if isinstance(dc, dict):
                                        text = dc.get("response") or dc.get("answer") or dc.get("result") or dc.get("content")
                                        if text:
                                            aggregated_text_parts.append(str(text))
                                            if want_text_output:
                                                for ev in yield_text_chunks_from(str(text)):
                                                    yield ev
                                            continue

                                # Not an Agora-style chunk. Check for top-level 'response' etc.
                                text = parsed.get("response") or parsed.get("answer") or parsed.get("result")
                                if text and isinstance(text, str):
                                    aggregated_text_parts.append(text)
                                    if want_text_output:
                                        for ev in (chunk_text_by_words(text, words_per_chunk=6)):
                                            out = {
                                                "id": stream_id,
                                                "object": "chat.completion.chunk",
                                                "choices": [{"delta": {"content": ev}}]
                                            }
                                            yield sse_event(out)
                                    continue

                                # fallback: stringify parsed and treat as text
                                flat = json.dumps(parsed, ensure_ascii=False)
                                aggregated_text_parts.append(flat)
                                if want_text_output:
                                    for piece in chunk_text_by_words(flat, words_per_chunk=6):
                                        out = {
                                            "id": stream_id,
                                            "object": "chat.completion.chunk",
                                            "choices": [{"delta": {"content": piece}}]
                                        }
                                        yield sse_event(out)
                                continue

                            # raw line (not JSON): treat as text chunk
                            aggregated_text_parts.append(line)
                            if want_text_output:
                                for piece in chunk_text_by_words(line, words_per_chunk=6):
                                    out = {
                                        "id": stream_id,
                                        "object": "chat.completion.chunk",
                                        "choices": [{"delta": {"content": piece}}]
                                    }
                                    yield sse_event(out)

                        # LightRAG stream finished. If audio output requested, synthesize audio from aggregated_text_parts
                        if want_audio_output:
                            final_text = None
                            # Prefer retrieving non-stream final result (best quality) if LightRAG provides it
                            try:
                                r2 = await call_lightrag_query(payload, headers)
                                if r2.status_code == 200:
                                    jr2 = r2.json()
                                    final_text = jr2.get("response") or jr2.get("answer") or jr2.get("result") or None
                            except Exception:
                                final_text = None
                            # fallback to aggregated text if final_text not available
                            if not final_text:
                                final_text = " ".join(aggregated_text_parts).strip()

                            if final_text:
                                final_text = clean_text_for_tts(final_text)
                                audio_bytes = tts_synthesize_bytes(final_text, fmt=(req.audio or {}).get("format", "pcm16"))
                                for b64_chunk in make_audio_base64_chunks(audio_bytes, chunk_size=1024):
                                    out = {
                                        "id": stream_id,
                                        "object": "chat.completion.chunk",
                                        "choices": [{"delta": {"audio": {"id": stream_id + "-audio", "data": b64_chunk}}}]
                                    }
                                    yield sse_event(out)

                        # Send final DONE
                        yield "data: [DONE]\n\n"
                        return
                    # else fallthrough to fallback
        except Exception:
            # ignore and fallback
            pass

        # Fallback: non-streaming query then chunk
        try:
            r = await call_lightrag_query(payload, headers)
        except Exception as e:
            err = {"id": stream_id, "object": "chat.completion.chunk", "choices": [{"delta": {"content": f"LightRAG request failed: {e}"}}]}
            yield sse_event(err)
            yield "data: [DONE]\n\n"
            return

        if r.status_code != 200:
            err = {"id": stream_id, "object": "chat.completion.chunk", "choices": [{"delta": {"content": f"LightRAG error: {r.status_code}"}}]}
            yield sse_event(err)
            yield "data: [DONE]\n\n"
            return

        jr = r.json()
        full_text = jr.get("response") or jr.get("answer") or jr.get("result") or json.dumps(jr)

        # If text output requested, stream text chunks
        if want_text_output:
            for piece in chunk_text_by_words(full_text, words_per_chunk=6):
                out = {
                    "id": stream_id,
                    "object": "chat.completion.chunk",
                    "choices": [{"delta": {"content": piece}}]
                }
                yield sse_event(out)
                await asyncio.sleep(0.02)

        # If audio output requested, synthesize and stream audio chunks (ensure audio chunks are delta.audio)
        if want_audio_output:
            cleaned = clean_text_for_tts(full_text)
            audio_bytes = tts_synthesize_bytes(cleaned, fmt=(req.audio or {}).get("format", "pcm16"))
            for b64_chunk in make_audio_base64_chunks(audio_bytes, chunk_size=1024):
                out = {
                    "id": stream_id,
                    "object": "chat.completion.chunk",
                    "choices": [{"delta": {"audio": {"id": stream_id + "-audio", "data": b64_chunk}}}]
                }
                yield sse_event(out)
                await asyncio.sleep(0.02)

        yield "data: [DONE]\n\n"
        return

    return StreamingResponse(stream_generator(), media_type="text/event-stream")

# Run with: uvicorn wrapper_multimodal_tts:app --host 0.0.0.0 --port 8080
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("wrapper_multimodal_tts:app", host="0.0.0.0", port=WRAPPER_PORT, log_level="info")
