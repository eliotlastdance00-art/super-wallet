from fastapi import APIRouter, Depends, HTTPException,status
from app.core.database import get_db
from .schemas import UserRegisterSchema
from .service  import UserService

router = APIRouter()

@router.post(
    "/register",
    summary="Register a new user",
    description="Creates a new user account with a unique username and email. Password must be at least 8 characters.",
    response_description="The newly created user's public data",
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Email or username already exists"},
        422: {"description": "Validation error - passwords do not match"},
    })
async def register(data: UserRegisterSchema, conn = Depends(get_db)):
    service = UserService(conn)
    try:
        return await service.register_user(data.username, data.email, data.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))