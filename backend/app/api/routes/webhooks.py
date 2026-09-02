from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.webhook_service import process_razorpay_webhook, WebhookVerificationError

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/razorpay")
async def razorpay_webhook_endpoint(
    request: Request,
    x_razorpay_signature: str | None = Header(None, alias="X-Razorpay-Signature"),
    x_razorpay_event_id: str | None = Header(None, alias="X-Razorpay-Event-Id"),
    db: Session = Depends(get_db),
):
    """
    Authoritative Razorpay Webhook receiver endpoint.
    Verifies cryptographic X-Razorpay-Signature and handles event deduplication.
    """
    body = await request.body()
    try:
        result = process_razorpay_webhook(
            raw_payload=body,
            signature_header=x_razorpay_signature,
            event_id_header=x_razorpay_event_id,
            db=db,
        )
        return result
    except WebhookVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
