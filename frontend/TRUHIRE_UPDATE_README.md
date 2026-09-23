# TruHire — Updated Frontend

This package contains the frontend source with a small API debugging helper.

## JD request expected by the current frontend

POST /api/job-descriptions

{
  "title": "<job title>",
  "jd_text": "<job description>"
}

The frontend API base remains `/api`, so Vite can proxy requests to the FastAPI backend.

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
