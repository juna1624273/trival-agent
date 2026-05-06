"""Session middleware — log requests and add request IDs."""

import time
import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all incoming requests with timing."""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        # Attach request_id to request state
        request.state.request_id = request_id

        logger.info(f"[{request_id}] {request.method} {request.url.path}")

        try:
            response = await call_next(request)
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[{request_id}] Error after {elapsed:.3f}s: {e}")
            raise

        elapsed = time.time() - start_time
        logger.info(f"[{request_id}] {response.status_code} ({elapsed:.3f}s)")

        response.headers[REQUEST_ID_HEADER] = request_id
        return response
