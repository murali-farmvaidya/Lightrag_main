# wrapper.py — Agora-compatible SSE streaming + strict non-stream JSON
import os
import json
import uuid
import asyncio
from typing import AsyncGenerator
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
import httpx
from pydantic import BaseModel

load_dotenv()

# Config (edit .env in repo root)
LIGHTRAG_URL = os.getenv("LIGHTRAG_URL", "http://localhost:9621/query")
LIGHTRAG_STREAM_URL = os.getenv("LIGHTRAG_STREAM_URL", LIGHTRAG_URL.rstrip("/") + "/stream")
WRAPPER_API_KEY = os.getenv("WRAPPER_API_KEY", "")     # optional wrapper auth
LIGHTRAG_API_KEY = os.getenv("LIGHTRAG_API_KEY", "")   # optional LightRAG auth
WRAPPER_PORT = int(os.getenv("WRAPPER_PORT", "8080"))
HTTP_TIMEOUT = int(os.getenv("WRAPPER_TIMEOUT", "60"))

app = FastAPI(title="Agora-compatible Custom LLM Wrapper")

# Input models
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatReq(BaseModel):
    model: str | None = None
    messages: list[ChatMessage] = []
    stream: bool | None = True

# Helpers
def extract_last_user(messages):
    for m in reversed(messages):
        if m.role.lower() == "user":
            return m.content
    return None

def chunk_text_by_words(text: str, words_per_chunk: int = 6):
    if not text:
        return []
    words = text.split()
    for i in range(0, len(words), words_per_chunk):
        yield " ".join(words[i:i+words_per_chunk])

async def call_lightrag_query(payload, headers):
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        return await client.post(LIGHTRAG_URL, json=payload, headers=headers, timeout=HTTP_TIMEOUT)

def sse_event(obj: dict) -> str:
    # Format chunk exactly as Agora expects
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

# Endpoint
@app.post("/chat/completions")
async def chat_completions(req: ChatReq, x_api_key: str | None = Header(None)):
    # AUTH: optional wrapper API key
    if WRAPPER_API_KEY and x_api_key != WRAPPER_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid wrapper API key")

    user_text = extract_last_user(req.messages)
    if not user_text:
        raise HTTPException(status_code=400, detail="No user message found")

    payload = {"query": user_text, "mode": "mix", "include_references": False}
    headers = {"Content-Type": "application/json"}
    if LIGHTRAG_API_KEY:
        headers["X-API-Key"] = LIGHTRAG_API_KEY

    # ----------------------
    # Non-streaming: strict OpenAI ChatCompletion (no extra fields)
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
    # Streaming mode: return SSE in Agora required chunk format
    # ----------------------
    stream_id = str(uuid.uuid4())

    async def stream_generator() -> AsyncGenerator[str, None]:
        # 1) Try to proxy LightRAG streaming endpoint if available
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", LIGHTRAG_STREAM_URL, json=payload, headers=headers) as resp:
                    if resp.status_code == 200:
                        # Helper: normalize text -> yield SSE events in small word chunks
                        def yield_text_chunks(text):
                            # split into small pieces to emulate token streaming
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

                            # Try parse JSON safely
                            parsed = None
                            try:
                                parsed = json.loads(line)
                            except Exception:
                                parsed = None

                            # 1) If parsed JSON exists
                            if isinstance(parsed, dict):
                                # Case A: parsed is already an Agora-style chunk object
                                if parsed.get("object") == "chat.completion.chunk":
                                    # try to extract delta.content
                                    try:
                                        choices = parsed.get("choices", [])
                                        if choices and isinstance(choices[0].get("delta", {}).get("content"), str):
                                            # already correct format: ensure id and forward
                                            parsed["id"] = stream_id
                                            yield sse_event(parsed)
                                            continue
                                        # delta.content is an object (not string) -> extract textual field
                                        dc = choices[0].get("delta", {}).get("content")
                                        if isinstance(dc, dict):
                                            # Look for likely textual keys
                                            text = dc.get("response") or dc.get("answer") or dc.get("result") or dc.get("content")
                                            if text:
                                                for ev in yield_text_chunks(str(text)):
                                                    yield ev
                                                continue
                                        # fallback: stringify delta and send as one chunk
                                        for ev in yield_text_chunks(json.dumps(dc, ensure_ascii=False)):
                                            yield ev
                                        continue
                                    except Exception:
                                        # safe fallback: stringify entire parsed JSON
                                        for ev in yield_text_chunks(json.dumps(parsed, ensure_ascii=False)):
                                            yield ev
                                        continue

                                # Case B: parsed is a plain object containing top-level 'response'/'answer' -> chunk it
                                text = parsed.get("response") or parsed.get("answer") or parsed.get("result")
                                if text and isinstance(text, str):
                                    for ev in yield_text_chunks(text):
                                        yield ev
                                    continue

                                # Case C: parsed is some other object -> try to find nested textual fields
                                # flatten and stringify as last resort
                                flat_text = None
                                for key in ("text", "content", "message", "data"):
                                    if parsed.get(key) and isinstance(parsed.get(key), str):
                                        flat_text = parsed.get(key)
                                        break
                                if flat_text:
                                    for ev in yield_text_chunks(flat_text):
                                        yield ev
                                    continue

                                # final fallback: stringify and send
                                for ev in yield_text_chunks(json.dumps(parsed, ensure_ascii=False)):
                                    yield ev
                                continue

                            # 2) Not JSON — treat as raw text
                            for ev in yield_text_chunks(line):
                                yield ev

                        # final DONE marker
                        yield "data: [DONE]\n\n"
                        return
                    # else: fallthrough to fallback chunking
        except Exception:
            # if streaming call failed, fallback below
            pass

        # 2) Fallback: call non-streaming /query and chunk the full text
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

        # chunk into small pieces (word groups) to emulate token streaming
        for piece in chunk_text_by_words(full_text, words_per_chunk=6):
            out = {
                "id": stream_id,
                "object": "chat.completion.chunk",
                "choices": [{"delta": {"content": piece}}]
            }
            yield sse_event(out)
            # small sleep to let Agora start processing chunks
            await asyncio.sleep(0.02)

        yield "data: [DONE]\n\n"
        return

    return StreamingResponse(stream_generator(), media_type="text/event-stream")

# Run with: uvicorn wrapper:app --host 0.0.0.0 --port 8080
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("wrapper:app", host="0.0.0.0", port=WRAPPER_PORT, log_level="info")
