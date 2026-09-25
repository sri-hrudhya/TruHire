# TruHire — Updated Frontend

This package contains the frontend source with a small API debugging helper.

## JD request expected by the current frontend

POST /api/job-descriptions

{
  "title": "<job title>",
  "jd_text": "<job description>"
}

The frontend API base remains `/api`, and Vite now proxies `/api` and `/uploads` to the FastAPI backend at `http://127.0.0.1:8999`.

## Important

The backend archive supplied in the conversation was a `.7z` file and could not be safely modified in this run. Therefore this ZIP contains the frontend updates only; no backend route/schema has been invented.

Use the browser Network tab to verify the request:
POST /api/job-descriptions

Expected statuses:
- 2xx: request reached backend successfully
- 401: authentication/token issue
- 404: backend route mismatch
- 422: Pydantic/request schema mismatch
- 500: backend exception


## Local backend port

The frontend is configured for the TruHire FastAPI backend on port **8999**. Start the backend from the project root with:

```powershell
uv run python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8999
```

Then start the frontend with `npm run dev` and open `http://localhost:5173`.
