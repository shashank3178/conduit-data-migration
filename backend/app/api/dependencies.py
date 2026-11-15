from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.user import User

bearer = HTTPBearer()


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


@lru_cache
def get_jwks_client():
    return PyJWKClient(
        f"https://{settings.auth0_domain}/.well-known/jwks.json"
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials

    try:
        signing_key = get_jwks_client().get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.auth0_audience,
            issuer=settings.auth0_issuer,
        )

        auth0_sub = payload["sub"]

    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token",
        ) from exc

    user = db.query(User).filter(User.auth0_sub == auth0_sub).first()

    if user is None:
        user = User(
            auth0_sub=auth0_sub,
            email=payload.get("email"),
        )

        db.add(user)
        db.commit()
        db.refresh(user)

    return user