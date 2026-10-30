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
docker compose down --remove-orphans
docker compose up --build -d

echo ""
echo "=================================================="
echo " TruHire is running!"
echo " Published URLs:"
echo " Web UI:       http://localhost:${FRONTEND_PORT:-3999}"
echo " API Docs:     http://localhost:${FRONTEND_PORT:-3999}/docs"
echo " Backend API:  http://localhost:${BACKEND_PORT:-8999}"
echo " OpenSearch:   http://localhost:${OPENSEARCH_PORT:-9200}"
echo " Dashboards:   http://localhost:5601"
echo "=================================================="
echo ""
echo "Running instances and published ports:"
docker compose ps
echo ""
echo "Useful commands:"
echo " Logs (all):       docker compose logs -f"
echo " Logs (backend):   docker compose logs -f backend"
echo " Status/ports:     docker compose ps"
echo " Stop containers:  docker compose down"
echo " Stop + volumes:   docker compose down -v"
