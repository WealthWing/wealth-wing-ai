from __future__ import annotations

import logging
from typing import Optional

from fastapi import Request, Response
from jwt import PyJWKClient, PyJWTError, decode
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.config import Settings, get_settings


logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Optional[Settings] = None):
        super().__init__(app)
        self.settings = settings or get_settings()
        self.JWKS_URL = self.settings.cognito_jwks_url
        self.COGNITO_USER_POOL_ID = self.settings.cognito_user_pool_id
        self.AWS_REGION = self.settings.aws_region
        self.COGNITO_ISSUER = self.settings.cognito_issuer
        self.CLIENT_ID = self.settings.cognito_client_id
        self.auth_is_configured = all(
            [self.JWKS_URL, self.COGNITO_ISSUER, self.CLIENT_ID]
        )
        if not self.JWKS_URL:
            logger.warning(
                "Cognito JWKS URL is not configured. Authentication will be unavailable."
            )
        
        self.jwks_client = (
            PyJWKClient(self.JWKS_URL) if self.auth_is_configured and self.JWKS_URL else None
        )
        self.public_paths = frozenset(self.settings.public_paths)

    async def dispatch(self, request: Request, call_next) -> Response:
        
        if request.url.path in self.public_paths:
            return await call_next(request)

        token = self._get_bearer_token(request)

        if not token:
            return self._error_response(request, 401, "Unauthorized")
        
        if self.jwks_client is None:
            logger.error("Auth middleware is missing required Cognito configuration")
            return self._error_response(
                request, 503, "Authentication service unavailable"
            )

        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            payload = decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.CLIENT_ID,
                issuer=self.COGNITO_ISSUER,
            )

            user_uuid = payload.get("sub")
            if not user_uuid:
                return self._error_response(request, 400, "Invalid token payload")

            request.state.user = payload
            request.state.user_uuid = user_uuid
            request.state.access_token = token
        except PyJWTError as e:
            logger.warning("JWT validation failed: %s", e)
            return self._error_response(request, 401, "Invalid token")
        except Exception:
            logger.exception("Unexpected authentication provider failure")
            return self._error_response(
                request, 503, "Authentication service unavailable"
            )

        response = await call_next(request)

        return response

    @staticmethod
    def _get_bearer_token(request: Request) -> Optional[str]:
        authorization = request.headers.get("Authorization")
        if not authorization:
            return None

        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return None

        return token.strip()

    @staticmethod
    def _error_response(request: Request, status_code: int, detail: str) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=status_code,
            content={"detail": detail, "request_id": request_id},
        )
