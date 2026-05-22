# TaskTriumph AI Task Generation Backend

An advanced, production-grade Python Flask microservice that powers intelligent learning resource harvesting, zero-key NLP categorization, and customized study plan generation.

---

## 🚀 Key Features

1. **Intelligent Domain Intent Analyzer**: Automatically normalizes user inputs using rapid fuzzy logic and scikit-learn models (e.g. maps "ML + Calculus" -> Standardized Categories & Tags).
2. **Quota-Free Hybrid Crawlers**: Scrapes educational YouTube playlists/videos, documentation cards (MDN, Microsoft, GeeksforGeeks), roadmap structures (roadmap.sh), and practice links (LeetCode, HackerRank) completely free.
3. **Multi-Option Selection**: Delivers 4-5 high-quality playlists, mixed options, and one-shot videos per learning domain.
4. **TTL Search Caching**: In-memory and disk TTL cache that optimizes response latency for repeat topics.
5. **Clean Pydantic Validation**: Ensures exact schema validation matching the frontend TypeScript models.

---

## 🛠️ Local Server Setup

### 1. Requirements
Ensure Python 3.10+ is installed on your system.

### 2. Startup Commands
Run the local Waitress-served backend using:
```bash
# Navigate to the backend folder
cd ai_task_backend

# Activate Virtual Environment
.\venv\Scripts\activate

# Run the backend
python app.py
```

The server runs on **`http://localhost:5000`** with full CORS handling.

---

## 🧪 Testing the APIs

You can quickly test the health and task generation endpoints using `curl` or Postman:

#### Health Check
```bash
curl http://localhost:5000/health
```

#### Task Generation
```bash
curl -X POST http://localhost:5000/generate-task \
  -H "Content-Type: application/json" \
  -d '{
    "taskTitle": "MERN Stack Auth",
    "concepts": "React Context, Node JWT authentication, MongoDB schema design",
    "duration": "2 weeks",
    "scheduleType": "daily",
    "resourcePreference": "playlist"
  }'
```
