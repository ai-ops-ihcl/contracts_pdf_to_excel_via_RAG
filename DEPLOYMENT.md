# IHCL Contract Pipeline - Deployment Guide

## 🚀 Quick Start

### 1. Prerequisites
- Docker & Docker Compose installed
- `.env` file configured (see below)

### 2. Start Services
```bash
# Start all services (Qdrant + API)
docker-compose up -d

# View logs
docker-compose logs -f app

# Stop services
docker-compose down
```

### 3. Access the API
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health
- Qdrant UI: http://localhost:6333/dashboard

## 📋 Environment Variables

Required variables in `.env`:

```bash
# --- Azure OpenAI (for embeddings & queries) ---
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key-here
AZURE_OPENAI_API_VERSION=2024-12-01-preview

# --- Azure Anthropic (Claude models) ---
ANTHROPIC_BASE_URL=https://your-resource.services.ai.azure.com/anthropic/
ANTHROPIC_API_KEY=your-key-here

# --- App Config ---
APP_NAME=ihcl-contract-pipeline
DEBUG=false

# --- Qdrant ---
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_COLLECTION=hotel_contracts

# --- Paths (container paths) ---
INPUT_PDF_DIR=./data/input_pdfs
PROCESSED_PDF_DIR=./data/processed_pdfs
MARKDOWN_DIR=./data/markdowns
OUTPUT_EXCEL_DIR=./data/output_excel
LOG_DIR=./data/logs

# --- Pipeline Settings ---
FUZZY_MATCH_THRESHOLD=80
MAX_WORKERS=4
```

## 📁 Directory Structure

```
pdf_to_md/
├── app/                      # Application code
│   ├── config.py            # Configuration
│   ├── main.py              # FastAPI app
│   ├── pipeline/            
│   │   └── orchestrator.py  # Pipeline orchestration
│   └── utils/               
│       ├── logger.py        # Logging utilities
│       └── tracker.py       # File tracking
├── data/                    # Mounted volume (persistent)
│   ├── input_pdfs/         # Upload PDFs here
│   ├── processed_pdfs/     # Processed PDFs moved here
│   ├── markdowns/          # Extracted markdown
│   ├── output_excel/       # Generated Excel files
│   └── logs/               # Pipeline logs
├── qdrant_storage/         # Qdrant data (persistent)
├── Dockerfile              # App container
├── docker-compose.yml      # Service orchestration
└── requirements.txt        # Python dependencies
```

## 🔄 API Endpoints

### Upload PDF
```bash
curl -X POST "http://localhost:8000/pipeline/upload" \
  -F "file=@contract.pdf" \
  -F "auto_run=true"
```

### Trigger Pipeline
```bash
# Incremental (new files only)
curl -X POST "http://localhost:8000/pipeline/run?mode=incremental"

# Full reprocessing
curl -X POST "http://localhost:8000/pipeline/run?mode=full"
```

### Check Status
```bash
curl http://localhost:8000/pipeline/status
```

### Download Latest Excel
```bash
curl -O http://localhost:8000/pipeline/download
```

### View History
```bash
curl http://localhost:8000/pipeline/history
```

## 🛠️ Troubleshooting

### Container won't start
```bash
# Check logs
docker-compose logs app

# Rebuild from scratch
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Qdrant connection issues
```bash
# Check Qdrant is healthy
docker-compose logs qdrant
curl http://localhost:6333/healthz

# Restart Qdrant
docker-compose restart qdrant
```

### Pipeline stuck
```bash
# Check status
curl http://localhost:8000/pipeline/status

# View app logs
docker-compose logs -f app

# Restart app
docker-compose restart app
```

### Reset tracker (reprocess all files)
```bash
curl -X POST http://localhost:8000/pipeline/reset
```

## 🔐 Security Notes

- **Never commit `.env`** - it contains API keys
- The `.env` file is gitignored
- In production, use secrets management (Azure Key Vault, etc.)
- Restrict network access to API (use reverse proxy, firewall)

## 📊 Monitoring

### Health Check
```bash
curl http://localhost:8000/health
```

Returns:
```json
{
  "status": "healthy",
  "service": "ihcl-contract-pipeline",
  "qdrant": "healthy",
  "input_pdfs_pending": 5,
  "output_excels": 3,
  "pipeline_running": false,
  "timestamp": "2026-06-03T12:00:00"
}
```

### View Logs
```bash
# Stream logs
docker-compose logs -f app

# Check log files
ls data/logs/
```

## 🚢 Production Deployment

### Azure Container Instances (ACI)
1. Build and push image to Azure Container Registry (ACR)
2. Deploy using `az container create`
3. Mount Azure File Share for data persistence
4. Use Azure Key Vault for secrets

### Azure Kubernetes Service (AKS)
1. Create deployment YAML with proper resource limits
2. Use persistent volume claims for data
3. Configure liveness/readiness probes
4. Set up autoscaling based on CPU/memory

### Azure App Service (Containers)
1. Push image to ACR
2. Create App Service (Linux, Docker)
3. Configure environment variables
4. Enable persistent storage
