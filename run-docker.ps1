Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " Starting TruHire in Docker..." -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

if (-not (Test-Path ".env")) {
    Write-Host "[INFO] No .env found. Copying .env.docker.example to .env..." -ForegroundColor Yellow
    Copy-Item ".env.docker.example" ".env"
    Write-Host "[INFO] .env created. Remember to add your LLM API key (e.g. GROQ_API_KEY) in .env!" -ForegroundColor Yellow
}

Write-Host "[INFO] Building and starting all containers..." -ForegroundColor Green
docker compose down --remove-orphans
docker compose up --build -d

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " TruHire is running!" -ForegroundColor Green
Write-Host " Published URLs:" -ForegroundColor White
Write-Host " Web UI:       http://localhost:$($env:FRONTEND_PORT ?? 3999)" -ForegroundColor White
Write-Host " API Docs:     http://localhost:$($env:FRONTEND_PORT ?? 3999)/docs" -ForegroundColor White
Write-Host " Backend API:  http://localhost:$($env:BACKEND_PORT ?? 8999)" -ForegroundColor White
Write-Host " OpenSearch:   http://localhost:$($env:OPENSEARCH_PORT ?? 9200)" -ForegroundColor White
Write-Host " Dashboards:   http://localhost:5601" -ForegroundColor White
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Running instances and published ports:" -ForegroundColor White
docker compose ps
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor White
Write-Host " Logs (all):       docker compose logs -f" -ForegroundColor Gray
Write-Host " Logs (backend):   docker compose logs -f backend" -ForegroundColor Gray
Write-Host " Status/ports:     docker compose ps" -ForegroundColor Gray
Write-Host " Stop containers:  docker compose down" -ForegroundColor Gray
Write-Host " Stop + volumes:   docker compose down -v" -ForegroundColor Gray
