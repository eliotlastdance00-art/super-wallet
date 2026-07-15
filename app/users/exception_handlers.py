from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.users.exception import (
    UsernameAlreadyExistsError,
    EmailAlreadyExistsError,
)


def register_users_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(UsernameAlreadyExistsError)
    async def username_exists_handler(request: Request, exc: UsernameAlreadyExistsError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(EmailAlreadyExistsError)
    async def email_exists_handler(request: Request, exc: EmailAlreadyExistsError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})