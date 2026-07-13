# core/security.py
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(raw_password: str) -> str:
    return pwd_context.hash(raw_password)