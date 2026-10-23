
import json
import logging
import logging.handlers
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

logger = logging.getLogger("sentinel.alert_handler")

#  Paths 
ROOT     = Path(__file__).resolve().parent.parent
LOG_DIR  = ROOT / "logs"
LOG_FILE = LOG_DIR / "sentinel.log"

#  ANSI colour codes
COLOURS = {
    "LOW":      "\033[92m",   # green
    "MEDIUM":   "\033[93m",   # yellow
    "HIGH":     "\033[33m",   # orange (bold yellow)
    "CRITICAL": "\033[91m",   # red
}
RESET  = "\033[0m"
BOLD   = "\033[1m"

ICONS = {
    "LOW":      "🟢",
    "MEDIUM":   "🟡",
    "HIGH":     "🟠",
    "CRITICAL": "🔴",
}


#  Public interface 

def dispatch(result) -> None:
    """
    Dispatch a RiskResult to console, log file, and SMS (CRITICAL only).
    Accepts either a RiskResult dataclass or a plain dict.
    """
    if hasattr(result, "to_dict"):
        data = result.to_dict()
    else:
        data = dict(result)

    _console(data)
    _log_ndjson(data)

    if data.get("alert_level") == "CRITICAL":
        _sms(data)


# Private helpers 
# receives risk result and dispatches to color coded console output 

def _console(data: dict) -> None:
    level  = data.get("alert_level", "LOW")
    score  = data.get("risk_score", 0)
    icon   = ICONS.get(level, "⚪")
    colour = COLOURS.get(level, "")
    flags  = data.get("reasons", [])

    print(f"\n{colour}{BOLD}{'─' * 56}{RESET}")
    print(f"{icon}  {colour}{BOLD}SENTINEL ALERT — {level}{RESET}  (score: {score}/100)")
    print(f"   Event : {data.get('event_type', 'unknown')}")
    print(f"   Time  : {data.get('timestamp', '')}")
    if flags:
        print(f"   Flags :")
        for f in flags:
            print(f"     • {f}")
    else:
        print(f"   Flags : none")
    print(f"{colour}{BOLD}{'─' * 56}{RESET}\n")

# dispatched the risk result to the rotating log file in NDJSON format
def _log_ndjson(data: dict) -> None:
    """Append one NDJSON line to the rotating sentinel.log file."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(data) + "\n")
    except Exception as exc:
        logger.error("Failed to write alert log: %s", exc)

# dispatched the risk result to Twilio for CRITICAL alerts only
def _sms(data: dict) -> None:
    """Send an SMS via Twilio for CRITICAL alerts."""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token  = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")
    to_number   = os.getenv("TWILIO_TO_NUMBER")

    if not all([account_sid, auth_token, from_number, to_number]):
        logger.warning("Twilio credentials not set — skipping SMS alert.")
        return

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)

        flags = data.get("reasons", [])
        top_flags = ", ".join(flags[:3]) if flags else "none"

        body = (
            f"🔴 SENTINEL CRITICAL ALERT\n"
            f"Score: {data.get('risk_score')}/100\n"
            f"Event: {data.get('event_type')}\n"
            f"Flags: {top_flags}\n"
            f"Time: {data.get('timestamp', '')[:19]}"
        )

        message = client.messages.create(
            body=body,
            from_=from_number,
            to=to_number,
        )
        logger.info("SMS alert sent | sid=%s", message.sid)
        print(f"📱 SMS alert sent ({message.sid})")

    except Exception as exc:
        logger.error("Failed to send SMS alert: %s", exc)