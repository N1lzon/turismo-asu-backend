import os
from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(_api_key_header)):
    expected = os.getenv("API_KEY")
    if not expected or api_key != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
