import os
from fastapi import Security, HTTPException, status, Depends
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from jose import JWTError, jwt

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/admin/auth/login")

def verify_api_key(api_key: str = Security(_api_key_header)):
    expected = os.getenv("API_KEY")
    if not expected or api_key != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

def verify_jwt(token: str = Depends(_oauth2_scheme)):
    try:
        jwt.decode(token, os.getenv("JWT_SECRET"), algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido o expirado")
