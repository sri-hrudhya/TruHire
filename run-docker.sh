#!/usr/bin/env bash
set -e

echo "=================================================="
echo " Starting TruHire in Docker..."
echo "=================================================="

# Check for .env file
if [ ! -f .env ]; then
  echo "[INFO] No .env found. Copying .env.docker.example to .env..."
  cp .env.docker.example .env
  echo "[INFO] .env created. Remember to add your LLM API key (e.g. GROQ_API_KEY) in .env!"
fi

echo "[INFO] Building and starting all containers..."
docker compose up --build -d

echo ""
echo "=================================================="
echo " TruHire is running!"
echo " Web UI:    http://localhost:3000"
echo " API Docs:  http://localhost:3000/docs (or :8999/docs)"
echo " OpenSearch: http://localhost:5601 (Dashboards)"
echo "=================================================="
echo "To view logs, run: docker compose logs -f"
echo "To stop, run:      docker compose down"

