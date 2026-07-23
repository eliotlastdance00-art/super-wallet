from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.outbox import OutboxRepository
from app.users.repository import UserRepository
from app.users.schemas.profile import (
    PasswordChangeRequest,
    UserProfileResponse,
    UserProfileUpdate,
)
from app.users.services.profile import (
    ProfileService,
    ProfileUpdateFields,
    RequestContext,
)

router = APIRouter()


def get_profile_service(conn=Depends(get_db)) -> ProfileService:
    return ProfileService(conn, UserRepository(conn), OutboxRepository(conn))


def get_request_context(request: Request) -> RequestContext:
    """
    Router-de bir gezek çözülýär, service-e taýýar geçirilýär - service
    HTTP-a bagly bolmasyn diýip (Request obýektini domen gatlagyna
    geçirmek layering-i bozar).
    """
    return RequestContext(
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


@router.get("/me", response_model=UserProfileResponse)
async def get_profile(
    user_id: Annotated[UUID, Depends(get_current_user)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> UserProfileResponse:
    user = await service.get_profile(user_id)
    return UserProfileResponse.model_validate(user)


@router.patch("/me", response_model=UserProfileResponse)
async def update_profile(
    payload: UserProfileUpdate,
    user_id: Annotated[UUID, Depends(get_current_user)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
    ctx: Annotated[RequestContext, Depends(get_request_context)],
) -> UserProfileResponse:
    """
    exclude_unset=True - munuň sebäbi PATCH semantikasy: iberilmedik
    meýdan "üýtgetme" diýip, "None-a öwür" diýip däl. Eger munsuz
    model_dump etsek, ulanyjy diňe email iberende-de username None
    bolup DB-de öçer.
    """
    fields = ProfileUpdateFields(**payload.model_dump(exclude_unset=True))
    await service.update_profile(user_id, fields, ctx)
    updated_user = await service.get_profile(user_id)
    return UserProfileResponse.model_validate(updated_user)


@router.patch("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChangeRequest,
    user_id: Annotated[UUID, Depends(get_current_user)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
    ctx: Annotated[RequestContext, Depends(get_request_context)],
) -> None:
    await service.change_password(
        user_id,
        current_password=payload.current_password.get_secret_value(),
        new_password=payload.new_password.get_secret_value(),
        ctx=ctx,
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    user_id: Annotated[UUID, Depends(get_current_user)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
    ctx: Annotated[RequestContext, Depends(get_request_context)],
) -> None:
    await service.deactivate_account(user_id, ctx)
