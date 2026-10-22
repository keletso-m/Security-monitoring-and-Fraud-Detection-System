
import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from engine.activity_detector import analyse
from engine.transaction_scorer import score as tx_score
from engine.risk_engine import evaluate
from alerts.alert_handler import dispatch
from app.auth.dependencies import require_admin

# slowapi imports for rate limiting
from fastapi import APIRouter, HTTPException, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger("sentinel.routes.activity")
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

# Request model 

class ActivityEvent(BaseModel):
    username:      str   = Field(...,  example="alice")
    ip_address:    str   = Field(...,  example="203.0.113.99")
    timestamp:     str   = Field(...,  example="2024-11-01T02:15:00")
    failed_logins: int   = Field(0,    ge=0, example=8)
    command:       str   = Field("",   example="cat /etc/passwd")


# Route 



@router.post("/activity", summary="Submit a system activity event")
@limiter.limit("120/minute")
def submit_activity(request: Request, event: ActivityEvent, _=Depends(require_admin)):
    """
    Analyse a system activity event for intrusion signals.

    Returns the full risk result including score, alert level, and reasons.
    The incident is persisted to the database automatically.
    """
    
    try:
        activity_result = analyse(event.model_dump())

        # Transaction scorer gets a zero score placeholder when only
        # an activity event is submitted the combined score still works
        transaction_result = tx_score({
            "account_id": event.username,
            "amount": 0,
            "currency": "",
            "location": "",
            "last_location": "",
            "device_id": "",
            "known_devices": [],
            "recent_tx_count": 0,
            "timestamp": event.timestamp,
        })

        result = evaluate(
            activity_result,
            transaction_result,
            context={"username": event.username, "ip_address": event.ip_address},
        )

        dispatch(result)

        logger.info(
            "Activity event processed | user=%s score=%d level=%s",
            event.username, result.risk_score, result.alert_level,
        )

        return result.to_dict()

    except Exception as exc:
        logger.error("Error processing activity event: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to process activity event.")

