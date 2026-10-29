Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " Starting TruHire in Docker..." -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

if (-not (Test-Path ".env")) {
    Write-Host "[INFO] No .env found. Copying .env.docker.example to .env..." -ForegroundColor Yellow
    Copy-Item ".env.docker.example" ".env"
    Write-Host "[INFO] .env created. Remember to add your LLM API key (e.g. GROQ_API_KEY) in .env!" -ForegroundColor Yellow
}

Write-Host "[INFO] Building and starting all containers..." -ForegroundColor Green
docker compose up --build -d

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " TruHire is running!" -ForegroundColor Green
Write-Host " Web UI:    http://localhost:3000" -ForegroundColor White
Write-Host " API Docs:  http://localhost:3000/docs" -ForegroundColor White
Write-Host " OpenSearch: http://localhost:5601" -ForegroundColor White
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "To view logs, run: docker compose logs -f" -ForegroundColor Gray
Write-Host "To stop, run:      docker compose down" -ForegroundColor Gray

