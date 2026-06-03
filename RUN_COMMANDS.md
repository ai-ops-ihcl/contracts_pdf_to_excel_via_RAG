# 🚀 How to Run the IHCL Contract Pipeline

## ⚠️ IMPORTANT: Qdrant Version Compatibility Issue

Your `./qdrant_local` folder was created with an older Qdrant client version and is incompatible with the current version. You have two options:

### Option 1: Delete Old Qdrant Data (Recommended for fresh start)
```bash
# Remove old incompatible data
rm -rf qdrant_local

# OR on Windows:
rmdir /s /q qdrant_local
```

### Option 2: Use Docker (Recommended for deployment)
Docker will use a fresh Qdrant instance, avoiding this issue entirely.

---

## 🐳 Method 1: Run with Docker (RECOMMENDED)

This is the **production deployment method** and avoids all local compatibility issues.

### Step 1: Ensure .env is configured
```bash
# Check that .env has all required keys
cat .env
```

### Step 2: Start all services
```bash
# Build and start containers
docker-compose up --build -d

# View logs
docker-compose logs -f app
```

### Step 3: Access the API
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health
- **Qdrant Dashboard**: http://localhost:6333/dashboard

### Step 4: Upload a PDF and trigger pipeline
```bash
# Upload a test PDF
curl -X POST "http://localhost:8000/pipeline/upload" \
  -F "file=@path/to/test.pdf" \
  -F "auto_run=true"

# Check status
curl http://localhost:8000/pipeline/status

# Download result
curl -O http://localhost:8000/pipeline/download
```

### Useful Docker Commands
```bash
# Stop services
docker-compose down

# Restart app only
docker-compose restart app

# View app logs
docker-compose logs -f app

# View Qdrant logs
docker-compose logs -f qdrant

# Rebuild after code changes
docker-compose build app
docker-compose up -d app

# Clean everything and start fresh
docker-compose down -v
docker-compose up --build -d
```

---

## 💻 Method 2: Run Locally (Development)

This runs the FastAPI app directly on your machine without Docker.

### Prerequisites
```bash
# 1. Remove old Qdrant data
rm -rf qdrant_local
# OR: rmdir /s /q qdrant_local

# 2. Install dependencies
pip install -r requirements.txt

# 3. Ensure .env is configured
```

### Start Qdrant Separately
You need Qdrant running. Either:

**Option A: Use Docker for Qdrant only**
```bash
docker run -d -p 6333:6333 -p 6334:6334 \
  -v $(pwd)/qdrant_storage:/qdrant/storage:z \
  qdrant/qdrant:v1.11.0
```

**Option B: Install Qdrant locally**
```bash
# Download from https://github.com/qdrant/qdrant/releases
# Or use Docker as above
```

### Start FastAPI App
```bash
# Run with uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# The --reload flag auto-restarts on code changes (dev mode)
```

### Access the API
- **API Docs**: http://localhost:8000/docs
- **Health**: http://localhost:8000/health

---

## 🧪 Testing

### Quick Health Check
```bash
curl http://localhost:8000/health
```

**Expected Output:**
```json
{
  "status": "healthy",
  "service": "ihcl-contract-pipeline",
  "qdrant": "healthy",
  "input_pdfs_pending": 0,
  "output_excels": 0,
  "pipeline_running": false,
  "timestamp": "2026-06-03T..."
}
```

### Test Pipeline End-to-End

1. **Upload a PDF**
```bash
curl -X POST "http://localhost:8000/pipeline/upload" \
  -F "file=@test.pdf"
```

2. **Trigger Processing**
```bash
curl -X POST "http://localhost:8000/pipeline/run?mode=incremental"
```

3. **Check Status**
```bash
curl http://localhost:8000/pipeline/status
```

4. **Download Result**
```bash
curl http://localhost:8000/pipeline/download -o output.xlsx
```

---

## 📋 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Check API and Qdrant health |
| `/pipeline/upload` | POST | Upload PDF (optionally auto-run) |
| `/pipeline/run` | POST | Trigger pipeline (incremental/full) |
| `/pipeline/status` | GET | Current run status |
| `/pipeline/history` | GET | Past run history |
| `/pipeline/download` | GET | Download latest Excel |
| `/pipeline/outputs` | GET | List all output files |
| `/pipeline/reset` | POST | Reset tracker (reprocess all) |
| `/docs` | GET | Interactive API documentation |

---

## 🛑 Troubleshooting

### "Qdrant unreachable" or "unhealthy"
```bash
# Check if Qdrant is running
docker-compose logs qdrant

# Or if using local Qdrant:
curl http://localhost:6333/healthz
```

### "Module not found" errors
```bash
# Ensure you're in the project root
pwd

# Reinstall dependencies
pip install -r requirements.txt
```

### "Pipeline stuck" or "already running"
```bash
# Check status
curl http://localhost:8000/pipeline/status

# Restart the app
docker-compose restart app
# OR if running locally: Ctrl+C and restart uvicorn
```

### Old Qdrant data compatibility issues
```bash
# Remove old data
rm -rf qdrant_local
rm -rf qdrant_storage

# Restart
docker-compose down -v
docker-compose up -d
```

---

## 🎯 Quick Start Commands (TL;DR)

**For Docker (Production)**:
```bash
rm -rf qdrant_local  # Clean old data
docker-compose up --build -d
docker-compose logs -f app
# Visit http://localhost:8000/docs
```

**For Local Development**:
```bash
rm -rf qdrant_local  # Clean old data
docker run -d -p 6333:6333 qdrant/qdrant:v1.11.0  # Start Qdrant
uvicorn app.main:app --reload  # Start API
# Visit http://localhost:8000/docs
```

---

## 📚 More Information

- **Full Deployment Guide**: See [DEPLOYMENT.md](DEPLOYMENT.md)
- **Technical Review**: See [DEPLOYMENT_REVIEW.md](DEPLOYMENT_REVIEW.md)
- **API Documentation**: http://localhost:8000/docs (when running)

---

**Last Updated**: 2026-06-03
