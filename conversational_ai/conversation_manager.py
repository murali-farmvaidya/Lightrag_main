import json
import os
import re
import requests

LIGHTRAG_URL = "http://localhost:9621/query"
SESSION_FILE = "session_store.json"


class ConversationManager:
    def __init__(self):
        self.sessions = self._load_sessions()

    # ---------------- FILE STORAGE ----------------
    def _load_sessions(self):
        if not os.path.exists(SESSION_FILE):
            return {}
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_sessions(self):
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(self.sessions, f, indent=2, ensure_ascii=False)

    # ---------------- SESSION ----------------
    def start_session(self, session_id):
        self.sessions[session_id] = {
            "history": [],
            "followup_count": 0
        }
        self._save_sessions()

    def reset_session(self, session_id):
        self.sessions.pop(session_id, None)
        self._save_sessions()

    # ---------------- HISTORY ----------------
    def add_user(self, session_id, text):
        self.sessions[session_id]["history"].append(
            {"role": "user", "content": text}
        )
        self._save_sessions()

    def add_assistant(self, session_id, text):
        self.sessions[session_id]["history"].append(
            {"role": "assistant", "content": text}
        )
        self._save_sessions()

    # ---------------- RULE-BASED DIRECT QUESTIONS ----------------
    def is_direct_knowledge_question(self, text: str) -> bool:
        keywords = [
            "what is", "explain", "tell me",
            "usage", "how is it used",
            "dosage", "benefits", "features"
        ]

        products = [
            "aadhaar gold",
            "poshak",
            "invictus",
            "zn-factor",
            "biofactor",
            "farmvaidya"
        ]

        t = text.lower()
        return any(k in t for k in keywords) and any(p in t for p in products)

    def is_program_or_fee_question(self, text: str) -> bool:
        keywords = [
            "fee", "fees", "cost", "price",
            "timing", "duration", "schedule",
            "program", "course", "training",
            "workshop", "certification",
            "ai in agriculture"
        ]

        t = text.lower()
        return any(k in t for k in keywords)

    def is_logistics_or_registration_question(self, text: str) -> bool:
        keywords = [
            "link",
            "register",
            "registration",
            "join",
            "zoom",
            "session link",
            "contact",
            "phone",
            "number",
            "how to join",
            "where to register"
        ]

        t = text.lower()
        return any(k in t for k in keywords)

    # ---------------- FOLLOW-UP DECISION ----------------
    def needs_follow_up(self, session_id) -> bool:
        history = self.sessions[session_id]["history"]

        payload = {
            "query": (
                "You are an agriculture assistant.\n\n"
                "Ask a follow-up question ONLY IF:\n"
                "- The answer depends on farmer-specific inputs "
                "(crop type, symptoms, soil condition, growth stage, location).\n\n"
                "DO NOT ask follow-up questions for:\n"
                "- Product explanations\n"
                "- Programs, fees, timings\n"
                "- Definitions or general info\n\n"
                "Reply ONLY with:\n"
                "ANSWER_DIRECTLY or ASK_FOLLOW_UP"
            ),
            "mode": "bypass",
            "conversation_history": history,
            "response_type": "Single Sentence"
        }

        try:
            res = requests.post(LIGHTRAG_URL, json=payload, timeout=30).json()
            decision = res.get("response", "").strip().upper()
            return decision == "ASK_FOLLOW_UP"
        except Exception:
            return False  # fail-safe

    def should_finalize(self, session_id):
        return self.sessions[session_id]["followup_count"] >= 2

    # ---------------- FOLLOW-UP ----------------
    def generate_followup(self, session_id):
        history = self.sessions[session_id]["history"]

        payload = {
            "query": "Ask ONE clear follow-up question to get missing farmer-specific details.",
            "mode": "bypass",
            "conversation_history": history,
            "response_type": "Single Sentence"
        }

        res = requests.post(LIGHTRAG_URL, json=payload, timeout=30).json()
        question = res.get("response", "").strip()

        self.sessions[session_id]["followup_count"] += 1
        self._save_sessions()
        return question

    # ---------------- FINAL ANSWER ----------------
    def final_answer(self, session_id):
        history = self.sessions[session_id]["history"]

        payload = {
            "query": history[-1]["content"],
            "mode": "mix",
            "conversation_history": history,
            "include_references": False,
            "response_type": "Multiple Paragraphs"
        }

        res = requests.post(LIGHTRAG_URL, json=payload, timeout=60).json()
        answer = res.get("response", "")
        return self._remove_references(answer)

    # ---------------- CLEANER ----------------
    def _remove_references(self, text: str) -> str:
        # Remove reference section
        text = re.split(r"\n\s*(###\s*)?references\s*\n", text, flags=re.IGNORECASE)[0]
        # Remove inline citations
        text = re.sub(r"\[\d+\]", "", text)
        return text.strip()
