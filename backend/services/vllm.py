"""
TruHire vLLM client.

Chat:
    DGX vLLM OpenAI-compatible API
    http://localhost:8000/v1

Embeddings:
    Requires a REAL embedding model exposed through an OpenAI-compatible
    /v1/embeddings endpoint.

The Qwen3.6-35B-A3B-NVFP4 generation model currently running on the DGX
does NOT automatically provide /v1/embeddings, so embeddings must use
a separate embedding server/model.

Environment variables:

    VLLM_BASE_URL=http://localhost:8000/v1
    VLLM_MODEL=nvidia/Qwen3.6-35B-A3B-NVFP4
    VLLM_API_KEY=EMPTY
    VLLM_TIMEOUT=120

Optional embedding configuration:

    EMBEDDING_BASE_URL=http://localhost:8001/v1
    VLLM_EMBEDDING_MODEL=<real embedding model>
    VLLM_EMBEDDING_API_KEY=EMPTY

or:

    EMBEDDING_BASE_URL=http://localhost:8001/v1
    EMBEDDING_MODEL=<real embedding model>
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from backend.config import settings


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def _normalise_base_url(url: str) -> str:
    """
    Normalize an OpenAI-compatible base URL.

    Examples:

        http://localhost:8000/v1/
        -> http://localhost:8000/v1

        http://localhost:8000
        -> http://localhost:8000/v1
    """
    url = (url or "").strip().rstrip("/")

    if not url:
        raise RuntimeError("API base URL is empty.")

    if not url.endswith("/v1"):
        url = f"{url}/v1"

    return url


def _headers(api_key: Optional[str] = None) -> Dict[str, str]:
    """
    Build HTTP headers.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    if api_key:
        key = api_key.strip()

        # EMPTY is commonly used with local vLLM servers.
        if key and key.upper() != "EMPTY":
            headers["Authorization"] = f"Bearer {key}"

    return headers


def _vllm_base_url() -> str:
    """
    DGX vLLM generation endpoint.
    """
    return _normalise_base_url(settings.VLLM_BASE_URL)


def _embedding_base_url() -> str:
    """
    Embedding endpoint.

    Priority:

    1. EMBEDDING_BASE_URL
    2. VLLM_EMBEDDING_BASE_URL
    3. VLLM_BASE_URL

    The third option is retained only so the application can detect that
    the current vLLM server does not expose embeddings.
    """

    embedding_url = getattr(settings, "EMBEDDING_BASE_URL", None)

    if not embedding_url:
        embedding_url = getattr(
            settings,
            "VLLM_EMBEDDING_BASE_URL",
            None,
        )

    if embedding_url:
        return _normalise_base_url(embedding_url)

    return _vllm_base_url()


def _vllm_api_key() -> Optional[str]:
    return getattr(settings, "VLLM_API_KEY", None)


def _embedding_api_key() -> Optional[str]:
    """
    Allow a separate API key for the embedding service.

    Falls back to VLLM_API_KEY.
    """
    key = getattr(settings, "VLLM_EMBEDDING_API_KEY", None)

    if key:
        return key

    return _vllm_api_key()


# ---------------------------------------------------------------------------
# Health / model discovery
# ---------------------------------------------------------------------------

def list_models(
    *,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> List[str]:
    """
    Return models exposed by an OpenAI-compatible server.

    GET:
        /v1/models
    """

    url = _normalise_base_url(
        base_url or settings.VLLM_BASE_URL
    )

    headers = _headers(
        api_key if api_key is not None else _vllm_api_key()
    )

    try:
        with httpx.Client(
            timeout=settings.VLLM_TIMEOUT
        ) as client:

            response = client.get(
                f"{url}/models",
                headers=headers,
            )

            response.raise_for_status()

            data = response.json()

    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Model discovery failed: "
            f"{exc.response.status_code} "
            f"{exc.response.text}"
        ) from exc

    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Could not connect to vLLM at {url}: {exc}"
        ) from exc

    models: List[str] = []

    for item in data.get("data", []):
        model_id = item.get("id")

        if model_id:
            models.append(str(model_id))

    return models


def vllm_health_check() -> bool:
    """
    Check whether the DGX vLLM server is reachable.
    """

    url = _vllm_base_url()

    try:
        with httpx.Client(
            timeout=min(float(settings.VLLM_TIMEOUT), 10.0)
        ) as client:

            response = client.get(
                f"{url}/models",
                headers=_headers(_vllm_api_key()),
            )

            return response.status_code == 200

    except httpx.HTTPError:
        return False


# ---------------------------------------------------------------------------
# Chat model
# ---------------------------------------------------------------------------

def resolve_chat_model() -> str:
    """
    Resolve the model used for chat/completions.
    """

    configured_model = getattr(
        settings,
        "VLLM_MODEL",
        None,
    )

    if configured_model:
        return configured_model

    models = list_models()

    if not models:
        raise RuntimeError(
            "DGX/vLLM returned no models. "
            "Set VLLM_MODEL in .env."
        )

    return models[0]


# ---------------------------------------------------------------------------
# Embedding model
# ---------------------------------------------------------------------------

def resolve_embedding_model() -> str:
    """
    Resolve the REAL embedding model.

    IMPORTANT:
    Never fall back to VLLM_MODEL here.

    A generation model such as:

        nvidia/Qwen3.6-35B-A3B-NVFP4

    is not automatically an embedding model.
    """

    configured_model = getattr(
        settings,
        "VLLM_EMBEDDING_MODEL",
        None,
    )

    if configured_model:
        return configured_model

    configured_model = getattr(
        settings,
        "EMBEDDING_MODEL",
        None,
    )

    if configured_model:
        return configured_model

    embedding_url = _embedding_base_url()

    models = list_models(
        base_url=embedding_url,
        api_key=_embedding_api_key(),
    )

    if not models:
        raise RuntimeError(
            "No embedding model configured.\n"
            f"Embedding endpoint: {embedding_url}\n\n"
            "Set one of:\n"
            "  VLLM_EMBEDDING_MODEL=<embedding-model>\n"
            "  EMBEDDING_MODEL=<embedding-model>\n\n"
            "Do NOT use the Qwen generation model as the embedding model."
        )

    if len(models) > 1:
        print(
            "[TruHire] Multiple embedding-server models found. "
            f"Using first model: {models[0]}"
        )

    return models[0]


# ---------------------------------------------------------------------------
# Embedding endpoint detection
# ---------------------------------------------------------------------------

def embedding_endpoint_available() -> bool:
    """
    Check whether the configured embedding server actually exposes
    POST /v1/embeddings.

    Important:
    A GET request cannot reliably prove endpoint availability because
    many OpenAI-compatible servers only implement POST.

    Therefore we inspect the server's OpenAPI document when possible.
    """

    base_url = _embedding_base_url()

    # Try OpenAPI first.
    openapi_urls = [
        base_url.rsplit("/v1", 1)[0] + "/openapi.json",
        base_url + "/openapi.json",
    ]

    for openapi_url in openapi_urls:
        try:
            with httpx.Client(
                timeout=10.0
            ) as client:

                response = client.get(openapi_url)

                if response.status_code != 200:
                    continue

                spec = response.json()

                paths = spec.get("paths", {})

                if "/v1/embeddings" in paths:
                    return True

                if "/embeddings" in paths:
                    return True

        except Exception:
            continue

    # We cannot conclusively prove it exists.
    return False


# ---------------------------------------------------------------------------
# Generate embedding
# ---------------------------------------------------------------------------

def generate_embedding(text: str) -> List[float]:
    """
    Generate a vector from a REAL embedding endpoint.

    This function intentionally does NOT call the DGX Qwen generation
    model's /v1/embeddings endpoint unless that server actually supports
    embeddings.

    Returns:
        List[float]
    """

    if not text or not text.strip():
        raise ValueError(
            "Cannot generate an embedding from empty text."
        )

    base_url = _embedding_base_url()
    model = resolve_embedding_model()

    payload: Dict[str, Any] = {
        "model": model,
        "input": text,
    }

    headers = _headers(
        _embedding_api_key()
    )

    endpoint = f"{base_url}/embeddings"

    try:
        with httpx.Client(
            timeout=settings.VLLM_TIMEOUT
        ) as client:

            response = client.post(
                endpoint,
                headers=headers,
                json=payload,
            )

    except httpx.ConnectError as exc:
        raise RuntimeError(
            "Embedding service is unreachable.\n"
            f"Endpoint: {endpoint}\n"
            f"Model: {model}\n\n"
            "Start the embedding server or configure "
            "EMBEDDING_BASE_URL correctly."
        ) from exc

    except httpx.TimeoutException as exc:
        raise RuntimeError(
            "Embedding request timed out.\n"
            f"Endpoint: {endpoint}\n"
            f"Model: {model}"
        ) from exc

    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Embedding HTTP request failed: {exc}"
        ) from exc

    # ---------------------------------------------------------------
    # Explicit 404 handling
    # ---------------------------------------------------------------

    if response.status_code == 404:

        raise RuntimeError(
            "Embedding endpoint returned HTTP 404.\n\n"
            f"Endpoint: {endpoint}\n"
            f"Model: {model}\n\n"
            "Your current DGX vLLM server exposes the generation model "
            "but does NOT expose /v1/embeddings.\n\n"
            "Do not set VLLM_EMBEDDING_MODEL to the Qwen generation model "
            "unless the server is started with an actual embedding model.\n\n"
            "Recommended architecture:\n"
            "  DGX :8000 -> Qwen generation\n"
            "  DGX :8001 -> embedding model\n"
            "  DGX :6333 -> Qdrant\n"
        )

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Embedding request failed "
            f"({response.status_code}): "
            f"{response.text}"
        ) from exc

    try:
        data = response.json()
    except Exception as exc:
        raise RuntimeError(
            "Embedding server returned invalid JSON:\n"
            f"{response.text[:1000]}"
        ) from exc

    # ---------------------------------------------------------------
    # Validate OpenAI-compatible response
    # ---------------------------------------------------------------

    embedding_data = data.get("data")

    if not embedding_data:
        raise RuntimeError(
            "Embedding server returned no data.\n"
            f"Response: {data}"
        )

    embedding = embedding_data[0].get("embedding")

    if not embedding:
        raise RuntimeError(
            "Embedding server returned an empty embedding.\n"
            f"Response: {data}"
        )

    try:
        vector = [float(value) for value in embedding]
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "Embedding server returned a non-numeric vector."
        ) from exc

    if not vector:
        raise RuntimeError(
            "Embedding vector is empty."
        )

    return vector


# ---------------------------------------------------------------------------
# Chat completion
# ---------------------------------------------------------------------------

def chat_completion(
    messages: List[Dict[str, str]],
    *,
    temperature: float = 0.2,
    max_tokens: int = 800,
) -> str:
    """
    Generate a chat completion using the DGX Qwen model.
    """

    if not messages:
        raise ValueError(
            "messages cannot be empty."
        )

    model = resolve_chat_model()

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    base_url = _vllm_base_url()
    endpoint = f"{base_url}/chat/completions"

    headers = _headers(
        _vllm_api_key()
    )

    try:
        with httpx.Client(
            timeout=settings.VLLM_TIMEOUT
        ) as client:

            response = client.post(
                endpoint,
                headers=headers,
                json=payload,
            )

    except httpx.ConnectError as exc:
        raise RuntimeError(
            "Could not connect to DGX vLLM.\n"
            f"Endpoint: {endpoint}"
        ) from exc

    except httpx.TimeoutException as exc:
        raise RuntimeError(
            "DGX vLLM chat request timed out.\n"
            f"Endpoint: {endpoint}"
            f"\nModel: {model}"
        ) from exc

    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"DGX vLLM request failed: {exc}"
        ) from exc

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"DGX vLLM returned "
            f"{response.status_code}: "
            f"{response.text}"
        ) from exc

    try:
        data = response.json()
    except Exception as exc:
        raise RuntimeError(
            "DGX vLLM returned invalid JSON:\n"
            f"{response.text[:1000]}"
        ) from exc

    choices = data.get("choices")

    if not choices:
        raise RuntimeError(
            "DGX vLLM returned no choices.\n"
            f"Response: {data}"
        )

    message = choices[0].get("message") or {}

    content = message.get("content")

    if content is None:
        return ""

    return str(content)


# ---------------------------------------------------------------------------
# Convenience diagnostics
# ---------------------------------------------------------------------------

def get_connection_info() -> Dict[str, Any]:
    """
    Return diagnostic information useful for debugging TruHire.
    """

    info: Dict[str, Any] = {
        "vllm_base_url": _vllm_base_url(),
        "vllm_model": getattr(settings, "VLLM_MODEL", None),
        "embedding_base_url": _embedding_base_url(),
        "embedding_model": getattr(
            settings,
            "VLLM_EMBEDDING_MODEL",
            None,
        ) or getattr(
            settings,
            "EMBEDDING_MODEL",
            None,
        ),
    }

    try:
        info["vllm_models"] = list_models()
    except Exception as exc:
        info["vllm_models_error"] = str(exc)

    if info["embedding_base_url"] != info["vllm_base_url"]:
        try:
            info["embedding_models"] = list_models(
                base_url=info["embedding_base_url"],
                api_key=_embedding_api_key(),
            )
        except Exception as exc:
            info["embedding_models_error"] = str(exc)

    return info