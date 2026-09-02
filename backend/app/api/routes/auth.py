from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.services.auth_service import create_session_token, get_authenticated_customer_id
from app.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class SessionTokenRequest(BaseModel):
    customer_id: str = Field(min_length=1, description="Persona or customer identifier")


class SessionTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    customer_id: str
    expires_in: int


class CustomerIdentityResponse(BaseModel):
    customer_id: str
    authenticated: bool = True


@router.post("/session", response_model=SessionTokenResponse)
@router.post("/token", response_model=SessionTokenResponse)
def create_session_token_endpoint(req: SessionTokenRequest) -> SessionTokenResponse:
    """
    Authenticate or select persona identity and issue a signed HMAC session token.
    """
    settings = get_settings()
    token = create_session_token(
        customer_id=req.customer_id,
        expires_in_seconds=settings.session_expiry_seconds,
    )
    return SessionTokenResponse(
        access_token=token,
        token_type="bearer",
        customer_id=req.customer_id,
        expires_in=settings.session_expiry_seconds,
    )


@router.get("/me", response_model=CustomerIdentityResponse)
def get_current_user_endpoint(
    customer_id: str = Depends(get_authenticated_customer_id),
) -> CustomerIdentityResponse:
    """
    Returns the server-authoritative authenticated identity.
    """
    return CustomerIdentityResponse(
        customer_id=customer_id,
        authenticated=True,
    )
