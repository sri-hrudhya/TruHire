@echo off
echo ==================================================
echo  Starting TruHire in Docker...
echo ==================================================

if not exist .env (
    echo [INFO] No .env found. Copying .env.docker.example to .env...
    copy .env.docker.example .env
    echo [INFO] .env created. Remember to add your LLM API key (e.g. GROQ_API_KEY) in .env!
)

echo [INFO] Building and starting all containers...
docker compose down --remove-orphans
docker compose up --build -d

echo.
echo ==================================================
echo  TruHire is running!
echo  Published URLs:
echo  Web UI:       http://localhost:3999
echo  API Docs:     http://localhost:3999/docs
echo  Backend API:  http://localhost:8999
echo  OpenSearch:   http://localhost:9200
echo  Dashboards:   http://localhost:5601
echo ==================================================
echo.
echo Running instances and published ports:
docker compose ps
echo.
echo Useful commands:
echo  Logs (all):       docker compose logs -f
echo  Logs (backend):   docker compose logs -f backend
echo  Status/ports:     docker compose ps
echo  Stop containers:  docker compose down
echo  Stop + volumes:   docker compose down -v
