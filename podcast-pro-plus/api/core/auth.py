from __future__ import annotations

import logging
from typing import Any, Optional, cast

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session

from api.core.config import settings
from api.core.database import get_session
from api.core import crud
from api.models.user import User

logger = logging.getLogger(__name__)

# Local OAuth2 scheme used for dependency token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

try:  # pragma: no cover - optional in some builds
	from jose import JWTError, jwt
except ModuleNotFoundError as exc:  # pragma: no cover
	JWTError = Exception  # type: ignore[assignment]
	jwt = None  # type: ignore[assignment]
	_JOSE_IMPORT_ERROR: Optional[ModuleNotFoundError] = exc
else:
	_JOSE_IMPORT_ERROR = None


def _raise_jwt_missing(context: str) -> None:
	detail = (
		"Authentication service is misconfigured (missing JWT support). "
		"Please contact support."
	)
	if _JOSE_IMPORT_ERROR:
		logger.error("JWT dependency missing while %s: %s", context, _JOSE_IMPORT_ERROR)
	else:
		logger.error("JWT dependency missing while %s", context)
	raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


async def get_current_user(
	request: Request,
	session: Session = Depends(get_session),
	token: str = Depends(oauth2_scheme),
) -> User:
	"""Decode the JWT and return the current user or raise 401."""
	credentials_exception = HTTPException(
		status_code=status.HTTP_401_UNAUTHORIZED,
		detail="Could not validate credentials",
		headers={"WWW-Authenticate": "Bearer"},
	)
	if jwt is None:
		_raise_jwt_missing("validating credentials")
	try:
		jwt_mod = cast(Any, jwt)
		payload = jwt_mod.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
		email = payload.get("sub")
		if not isinstance(email, str) or not email:
			raise credentials_exception
	except JWTError:
		raise credentials_exception

	user = crud.get_user_by_email(session=session, email=email)
	if user is None:
		raise credentials_exception
	return user

__all__ = ["get_current_user", "oauth2_scheme"]
