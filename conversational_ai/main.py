from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from conversation_manager import ConversationManager
import os

app = FastAPI()
manager = ConversationManager()

# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ✅ Serve static files
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "static")),
    name="static"
)

# ---------------- HTML ----------------
@app.get("/")
def serve_chat_ui():
    return FileResponse(os.path.join(BASE_DIR, "chat.html"))

# ---------------- MODELS ----------------
class ChatMessage(BaseModel):
    session_id: str
    message: str

class ResetModel(BaseModel):
    session_id: str

# ---------------- CHAT ----------------
@app.post("/chat")
def chat(data: ChatMessage):
    sid = data.session_id
    msg = data.message.strip()

    if not msg:
        return {"type": "error", "response": "Empty message"}

    if sid not in manager.sessions:
        manager.start_session(sid)

    manager.add_user(sid, msg)

    if (
        manager.is_direct_knowledge_question(msg)
        or manager.is_program_or_fee_question(msg)
        or manager.is_logistics_or_registration_question(msg)
    ):
        answer = manager.final_answer(sid)
        manager.add_assistant(sid, answer)
        return {"type": "final_answer", "response": answer}

    if not manager.needs_follow_up(sid) or manager.should_finalize(sid):
        answer = manager.final_answer(sid)
        manager.add_assistant(sid, answer)
        return {"type": "final_answer", "response": answer}

    followup = manager.generate_followup(sid)
    manager.add_assistant(sid, followup)
    return {"type": "follow_up_question", "response": followup}

# ---------------- RESET ----------------
@app.post("/reset")
def reset(data: ResetModel):
    manager.reset_session(data.session_id)
    return {"status": "cleared", "session_id": data.session_id}
