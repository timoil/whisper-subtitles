from datetime import datetime, timedelta
from typing import Optional
import json
import os

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Bearer token
security = HTTPBearer(auto_error=False)

# Default credentials
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin123"


def get_config_data() -> dict:
    """Load config from file or return defaults."""
    if os.path.exists(settings.config_path):
        try:
            with open(settings.config_path, 'r') as f:
                return json.load(f)
        except:
            pass
    return {
        "password_hash": pwd_context.hash(DEFAULT_PASSWORD),
        "model": settings.default_model,
        "cpu_threads": settings.cpu_threads,
        "language": settings.default_language
    }


def save_config_data(data: dict):
    """Save config to file."""
    with open(settings.config_path, 'w') as f:
        json.dump(data, f, indent=2)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=settings.access_token_expire_hours))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def verify_token(token: str) -> Optional[dict]:
    """Verify a JWT token and return the payload."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except JWTError:
        return None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """Get the current authenticated user from the token."""
    token = None
    
    # Try to get token from Authorization header
    if credentials:
        token = credentials.credentials
    
    # Try to get token from cookie
    if not token:
        token = request.cookies.get("access_token")
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    return {"username": payload.get("sub", "admin")}


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """Authenticate a user with username and password."""
    if username != DEFAULT_USERNAME:
        return None
    
    config = get_config_data()
    if not verify_password(password, config["password_hash"]):
        return None
    
    return {"username": username}


def change_password(current_password: str, new_password: str) -> bool:
    """Change the admin password."""
    config = get_config_data()
    
    if not verify_password(current_password, config["password_hash"]):
        return False
    
    config["password_hash"] = hash_password(new_password)
    save_config_data(config)
    return True


def get_app_settings() -> dict:
    """Get current application settings."""
    config = get_config_data()
    return {
        "model": config.get("model", settings.default_model),
        "cpu_threads": config.get("cpu_threads", settings.cpu_threads),
        "language": config.get("language", settings.default_language),
        "available_models": settings.available_models
    }


def update_app_settings(model: Optional[str] = None, cpu_threads: Optional[int] = None, language: Optional[str] = None) -> dict:
    """Update application settings."""
    config = get_config_data()
    
    if model and model in settings.available_models:
        config["model"] = model
    if cpu_threads is not None and cpu_threads >= 0:
        config["cpu_threads"] = cpu_threads
    if language:
        config["language"] = language
    
    save_config_data(config)
    return get_app_settings()
