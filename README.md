# LightRAG + Conversational AI Chatbot

> A complete setup guide for building a custom conversational AI chatbot using LightRAG and OpenAI integration on Windows.

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.125.0-009688.svg)](https://fastapi.tiangolo.com/)

## 📋 Overview

This project combines LightRAG's powerful knowledge graph capabilities with a conversational AI chatbot to create an intelligent system that can:

- Process and understand custom documents (PDFs, DOCX, text)
- Maintain conversation context and ask intelligent follow-up questions
- Provide accurate answers based on your domain knowledge
- Integrate seamlessly with voice AI systems like Agora

## 🏗️ Architecture

```
┌─────────────────┐
│   User Browser  │
│  localhost:8000 │
└────────┬────────┘
         │
         ▼
┌────────────────────────┐
│  Conversational Chatbot│ ◄─── FastAPI + Session Management
│      (Port 8000)       │
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│   LightRAG Server      │ ◄─── Knowledge Graph + Vector Store
│      (Port 9621)       │
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│      OpenAI API        │ ◄─── GPT-4o-mini + Embeddings
└────────────────────────┘
```

## ✨ Features

- **Intelligent Document Processing**: Upload PDFs, DOCX files, or text to build your knowledge base
- **Conversational Interface**: Natural chat experience with context-aware responses
- **Follow-up Questions**: Automatically asks clarifying questions when needed
- **Multiple Query Modes**: Local, global, hybrid, naive, and mix modes for different use cases
- **Session Management**: Maintains conversation history per user
- **REST API**: Easy integration with external systems
- **Web UI**: Clean, responsive chat interface
- **Production Ready**: Deployment guide for Render.com included

## 🚀 Quick Start

### Prerequisites

- Windows 10/11
- Python 3.11+ (Python 3.13 recommended)
- OpenAI API Key ([Get it here](https://platform.openai.com/api-keys))
- Git for cloning repositories

### Installation

**⚠️ IMPORTANT**: You need **2 PowerShell terminals** running simultaneously.

#### Terminal 1: LightRAG Server

```powershell
# Clone repository
cd C:\Users\YourUsername\
git clone https://github.com/murali-farmvaidya/Convo_chatbot.git
cd LightRAG

# Install UV package manager
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
$env:Path = "C:\Users\$env:USERNAME\.local\bin;$env:Path"

# Create virtual environment and install dependencies
uv sync --extra api
.\.venv\Scripts\activate

# Install and setup Bun (for Web UI)
powershell -c "irm https://bun.sh/install.ps1 | iex"
$env:Path = "$env:USERPROFILE\.bun\bin;$env:Path"

# Build Web UI
cd lightrag_webui
bun install --frozen-lockfile
bun run build
cd ..

# Configure environment
copy env.example .env
notepad .env  # Add your OpenAI API key

# Start server
lightrag-server
```

#### Terminal 2: Conversational AI Chatbot

```powershell
# Navigate to chatbot directory
cd C:\Users\YourUsername\LightRAG\conversational_ai

# Create virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
notepad .env  # Add your configuration

# Start chatbot server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Access the Application

- **Chatbot Interface**: http://localhost:8000
- **LightRAG Swagger UI**: http://localhost:9621/docs
- **LightRAG Web Dashboard**: http://localhost:9621

## 🔧 Configuration

### LightRAG Server (.env)

```bash
# LLM Configuration
LLM_BINDING=openai
LLM_MODEL=gpt-4o-mini
LLM_BINDING_HOST=https://api.openai.com/v1
LLM_BINDING_API_KEY=sk-YOUR-OPENAI-API-KEY-HERE
MAX_TOKENS=32768
MAX_ASYNC=8

# Embedding Configuration
EMBEDDING_BINDING=openai
EMBEDDING_BINDING_HOST=https://api.openai.com/v1
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_BINDING_API_KEY=sk-YOUR-OPENAI-API-KEY-HERE
EMBEDDING_DIM=3072
EMBEDDING_SEND_DIM=false

# Storage
WORKING_DIR=./rag_storage
INPUT_DIR=./inputs

# API Server
LIGHTRAG_API_KEY=your-secret-api-key-here
HOST=0.0.0.0
PORT=9621
```

### Conversational Chatbot (.env)

```bash
# LightRAG Connection
LIGHTRAG_BASE_URL=http://localhost:9621
LIGHTRAG_API_KEY=your-secret-api-key-here

# OpenAI Configuration
OPENAI_API_KEY=sk-YOUR-OPENAI-API-KEY-HERE

# Server Configuration
CHATBOT_HOST=0.0.0.0
CHATBOT_PORT=8000

# Session Settings
MAX_FOLLOW_UPS=3
SESSION_TIMEOUT=1800
```

## 📚 Usage

### Upload Documents

Use the Swagger UI at http://localhost:9621/docs:

1. Click **Authorize** and enter your API key
2. Navigate to `POST /documents/upload`
3. Upload your PDF or DOCX files
4. Or use `POST /documents/text` to insert text directly

### Chat Interface

1. Open http://localhost:8000
2. Type your message and press Enter
3. The bot will respond using your uploaded knowledge
4. Click "New Chat" to start a fresh conversation

### API Integration

```bash
# Send a chat message
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "unique-session-id",
    "message": "What is your product?"
  }'

# Response
{
  "type": "final_answer",
  "response": "Based on our documentation..."
}
```

## 🎯 Query Modes

| Mode | Description | Best For |
|------|-------------|----------|
| `local` | Context-dependent search | Specific document queries |
| `global` | Global knowledge search | Broad topic questions |
| `hybrid` | Combined approach | **Most queries (recommended)** |
| `naive` | Basic keyword search | Simple lookups |
| `mix` | KG + vector retrieval | Complex multi-source queries |

## 🔌 API Endpoints

### Chatbot (Port 8000)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Chat interface (HTML) |
| `/chat` | POST | Send message, get response |
| `/reset` | POST | Clear conversation history |
| `/health` | GET | Health check |
| `/static/{file}` | GET | Static files (images) |

### LightRAG (Port 9621)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/documents/upload` | POST | Upload files |
| `/documents/text` | POST | Insert text |
| `/query` | POST | Query with complete response |
| `/query/stream` | POST | Streaming response |
| `/docs` | GET | Swagger UI |
| `/health` | GET | Health check |

## 🚀 Deployment

### Deploy to Render.com

1. Push your code to GitHub
2. Create new Web Service on [Render.com](https://render.com)
3. Connect your repository
4. Configure settings:
   - **Root Directory**: `conversational_ai`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables (see Configuration section)
6. Deploy!

Update `chat.html` with your production URL:

```javascript
const res = await fetch("https://your-app.onrender.com/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ session_id: sessionId, message })
});
```

## 🔧 Troubleshooting

### UV command not found

```powershell
$env:Path = "C:\Users\$env:USERNAME\.local\bin;$env:Path"
```

### Bun command not found

```powershell
$env:Path = "$env:USERPROFILE\.bun\bin;$env:Path"
```

### Vector count mismatch error

Ensure these are in your `.env`:

```bash
EMBEDDING_DIM=3072
EMBEDDING_SEND_DIM=false
```

Then clear storage:

```powershell
Remove-Item -Recurse -Force .\rag_storage -ErrorAction SilentlyContinue
lightrag-server
```

### Port already in use

```powershell
# LightRAG on different port
lightrag-server --port 8080

# Chatbot on different port
uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

### Static files not loading (404)

```powershell
pip install jinja2
New-Item -ItemType Directory -Force -Path static
# Copy logo.png and title.png to static folder
```

## 🎨 Agora AI Integration

This setup is ready for Agora voice AI integration:

**Integration Flow**:
1. Agora STT → Text
2. Send to chatbot: `POST /chat`
3. Chatbot processes via LightRAG
4. Returns answer text
5. Agora TTS → Speech

**API Endpoint**:
```
POST http://your-server:8000/chat
Body: {
  "session_id": "unique-user-id",
  "message": "User question from STT"
}

Response: {
  "type": "final_answer",
  "response": "Answer for TTS"
}
```

## 📁 Project Structure

```
LightRAG/
├── lightrag_webui/          # Web UI components
├── rag_storage/             # Knowledge base storage
├── inputs/                  # Input documents
├── conversational_ai/       # Chatbot application
│   ├── main.py             # FastAPI application
│   ├── conversation_manager.py
│   ├── chat.html           # Chat interface
│   ├── requirements.txt
│   ├── .env                # Configuration
│   └── static/             # Images (logo, icons)
├── .env                    # LightRAG configuration
└── README.md
```

## 🔒 Security Notes

**Never commit these files**:
- `.env`
- `*.env`
- `rag_storage/`
- `venv/` or `.venv/`
- `session_store.json`

Add to `.gitignore`:

```
.env
*.env
rag_storage/
venv/
.venv/
__pycache__/
*.pyc
session_store.json
*.log
```

## 📖 Additional Resources

- [LightRAG Documentation](https://github.com/HKUDS/LightRAG)
- [OpenAI API Keys](https://platform.openai.com/api-keys)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Agora Custom LLM Integration](https://docs.agora.io)

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 💬 Support

If you encounter issues:

1. Check the Troubleshooting section above
2. Review server logs in both terminals
3. Check browser console (F12) for errors
4. Verify environment variables are set correctly
5. Ensure both servers are running simultaneously

## 🎉 Acknowledgments

- LightRAG team for the amazing knowledge graph framework
- OpenAI for GPT models and embeddings
- FastAPI for the robust web framework

---

**Ready to build intelligent conversational AI! 🚀**

Made with ❤️ for seamless LLM integration