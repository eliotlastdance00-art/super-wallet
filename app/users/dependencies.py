# app/users/dependencies.py
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from app.core.database import get_db
from app.users.security import decode_access_token
from app.users.repository import UserRepository, UserRecord

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=True)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    conn=Depends(get_db),
) -> UserRecord:
    if token is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    repo = UserRepository(conn)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    return user