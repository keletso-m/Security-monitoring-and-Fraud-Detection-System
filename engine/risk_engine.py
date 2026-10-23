import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from engine.explainer import explain_flags, explain_severity

logger = logging.getLogger("sentinel.risk_engine")

#  DB path 
ROOT    = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "incidents.db"

#  Blending weights 
WEIGHT_ACTIVITY:    float = 1.0
WEIGHT_TRANSACTION: float = 0.0

#  alert level thresholds 
LEVEL_CRITICAL: int = 75
LEVEL_HIGH:     int = 50
LEVEL_MEDIUM:   int = 25


#  Result dataclass 

@dataclass
class RiskResult:
    risk_score:   int
    alert_level:  str
    reasons: list[str]
    event_type:   str
    timestamp:    str
    incident_id:  int | None = None
    context:      dict       = field(default_factory=dict)
    explanations:      list[str]  = field(default_factory=list)
    severity_rationale: str       = ""
    username:          str = "unknown"
    ip_address:        str = "unknown"
    activity_score:    int = 0
    transaction_score: int = 0


    def to_dict(self) -> dict:
        return {
            "id":           self.incident_id,
            "risk_score":   self.risk_score,
            "alert_level":  self.alert_level,
            "reasons":      self.reasons,
            "event_type":   self.event_type,
            "timestamp":    self.timestamp,
            "context":      self.context,
            "explanations":      self.explanations,
            "severity_rationale": self.severity_rationale,
            
        }

#  Public interface

def evaluate(
    activity_result:    dict,
    transaction_result: dict,
    context:            dict | None = None,

) -> RiskResult:
     
    context = context or {}

    activity_score    = int(activity_result.get("activity_score", 0))
    transaction_score = int(transaction_result.get("transaction_score", 0))

    blended     = int(activity_score * WEIGHT_ACTIVITY + transaction_score * WEIGHT_TRANSACTION)
    final_score = _clamp(blended)
    alert_level = _assign_level(final_score)

    all_reasons = (
        activity_result.get("reasons", []) +
        transaction_result.get("reasons", [])
    )

    event_type = _infer_event_type(activity_score, transaction_score)
    timestamp  = datetime.now(timezone.utc).isoformat()

    result = RiskResult(
        risk_score   = final_score,
        alert_level  = alert_level,
        reasons      = all_reasons, 
        event_type   = event_type,
        timestamp    = timestamp,
        context      = context,
        username      = context.get("username", "unknown"),
        ip_address    = context.get("ip_address", "unknown"),
        activity_score    = activity_score,
        transaction_score = transaction_score,
        incident_id   = None,
    )
     # generate human/ explaible explanations
    result.explanations       = explain_flags(all_reasons)
    result.severity_rationale = explain_severity(
        score             = final_score,
        alert_level       = alert_level,
        event_type        = event_type,
        activity_score    = activity_score,
        transaction_score = transaction_score,
    )

    result.incident_id = _persist(result)

    logger.info(
        "Risk evaluation complete | score=%d level=%s event=%s reasons=%d",
        final_score, alert_level, event_type, len(all_reasons),
    )

    return result

# Return recent incidents from the DB, newest first
def get_incidents(limit: int = 50, min_score: int = 0) -> list[dict]:
    try:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("""
            SELECT id, risk_score, alert_level, reason_flags, event_type, timestamp, state
            FROM incidents
            WHERE risk_score >= ?
            ORDER BY id DESC
            LIMIT ?
        """, (min_score, limit))
        rows = cur.fetchall()
        con.close()
        return [_row_to_dict(row) for row in rows]
    except Exception as exc:
        logger.error("Failed to fetch incidents: %s", exc)
        return []

# Return a single incident by ID, or None if not found
def get_incident_by_id(incident_id) -> dict | None:
    try:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("""
            SELECT id, risk_score, alert_level, reason_flags, event_type, timestamp, state
            FROM incidents
            WHERE id = ?
        """, (int(incident_id),))
        row = cur.fetchone()
        con.close()
        return _row_to_dict(row) if row else None
    except Exception as exc:
        logger.error("Failed to fetch incident %s: %s", incident_id, exc)
        return None

# incident states and severity workflow
VALID_STATES     = {"open", "investigating", "resolved", "false_positive"}
VALID_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def update_incident_state(incident_id: int, new_state: str, changed_by: str) -> bool:
    if new_state not in VALID_STATES:
        raise ValueError(f"Invalid state '{new_state}'. Must be one of {VALID_STATES}")
    return _update_incident_field(incident_id, "state", new_state, changed_by)


def update_incident_severity(incident_id: int, new_severity: str, changed_by: str) -> bool:
    if new_severity not in VALID_SEVERITIES:
        raise ValueError(f"Invalid severity '{new_severity}'. Must be one of {VALID_SEVERITIES}")
    return _update_incident_field(incident_id, "alert_level", new_severity, changed_by)


def get_incident_history(incident_id: int) -> list[dict]:
    """Returns the full audit trail for an incident, newest first."""
    try:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("""
            SELECT id, incident_id, changed_by, field, old_value, new_value, timestamp
            FROM incident_history
            WHERE incident_id = ?
            ORDER BY id DESC
        """, (incident_id,))
        rows = cur.fetchall()
        con.close()
        return [dict(row) for row in rows]
    except Exception as exc:
        logger.error("Failed to fetch history for incident %s: %s", incident_id, exc)
        return []


def _update_incident_field(
    incident_id: int, field: str, new_value: str, changed_by: str
) -> bool:
    """Generic field updater, reads old value, writes new, logs history."""
    column_map = {
        "state":       "state",
        "alert_level": "alert_level",
    }
    if field not in column_map:
        logger.error("Unknown field: %s", field)
        return False

    column = column_map[field]

    try:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row

        row = con.execute(
            f"SELECT {column} FROM incidents WHERE id = ?", (incident_id,)
        ).fetchone()

        if not row:
            con.close()
            return False

        old_value = row[column]

        con.execute(
            f"UPDATE incidents SET {column} = ? WHERE id = ?",
            (new_value, incident_id),
        )

        con.execute("""
            INSERT INTO incident_history
                (incident_id, changed_by, field, old_value, new_value, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            incident_id,
            changed_by,
            field,
            old_value,
            new_value,
            datetime.now(timezone.utc).isoformat(),
        ))

        con.commit()
        con.close()
        return True

    except Exception as exc:
        logger.error("Failed to update %s on incident %s: %s", field, incident_id, exc)
        return False


# helper functions

def _assign_level(score: int) -> str:
    if score >= LEVEL_CRITICAL:
        return "CRITICAL"
    if score >= LEVEL_HIGH:
        return "HIGH"
    if score >= LEVEL_MEDIUM:
        return "MEDIUM"
    return "LOW"


def _infer_event_type(activity_score: int, transaction_score: int) -> str:
    if activity_score > 0 and transaction_score > 0:
        return "combined"
    if transaction_score > 0:
        return "transaction"
    return "activity"


def _clamp(value: int) -> int:
    return min(max(value, 0), 100)


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id":           row["id"],
        "risk_score":   row["risk_score"],
        "alert_level":  row["alert_level"],
        "reason_flags": row["reason_flags"].split("|") if row["reason_flags"] else [],
        "event_type":   row["event_type"],
        "timestamp":    row["timestamp"],
        "state":        row["state"] if "state" in row.keys() else "open",
        "context":      json.loads(row["context"]) if "context" in row.keys() else {},
    }
# write the incident to SQLite and returns the new row ID, or None on failure
def _persist(result: RiskResult) -> int | None:
    
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("""
            INSERT INTO incidents
                (risk_score, alert_level, reason_flags, event_type, timestamp, context)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            result.risk_score,
            result.alert_level,
            "|".join(result.reasons),   
            result.event_type,
            result.timestamp,
            json.dumps(result.context),
        ))
        con.commit()
        row_id = cur.lastrowid
        con.close()
        return row_id
    except Exception as exc:
        logger.error("Failed to persist incident: %s", exc)
        import traceback
        traceback.print_exc()
        return None

def get_entity_history(entity_type: str, entity_value: str, limit: int = 50) -> dict:
    """Return all incidents and stats for a given username or IP address"""
    try:
        import json
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("""
            SELECT id, risk_score, alert_level, reason_flags, event_type, timestamp, state, context
            FROM incidents
            ORDER BY id DESC
        """)
        rows = cur.fetchall()
        con.close()

        # filter by entity
        matched = []
        for row in rows:
            try:
                ctx = json.loads(row["context"]) if row["context"] else {}
            except Exception:
                ctx = {}

            value = ctx.get("username") if entity_type == "username" else ctx.get("ip_address")
            if value and value.lower() == entity_value.lower():
                matched.append(row)

        matched = matched[:limit]

        if not matched:
            return {"entity_type": entity_type, "entity_value": entity_value, "count": 0, "incidents": [], "stats": {}}

        scores     = [r["risk_score"] for r in matched]
        severities = [r["alert_level"] for r in matched]

        stats = {
            "total_incidents": len(matched),
            "average_score":   round(sum(scores) / len(scores), 1),
            "highest_score":   max(scores),
            "lowest_score":    min(scores),
            "severity_counts": {
                "CRITICAL": severities.count("CRITICAL"),
                "HIGH":     severities.count("HIGH"),
                "MEDIUM":   severities.count("MEDIUM"),
                "LOW":      severities.count("LOW"),
            },
        }

        return {
            "entity_type":  entity_type,
            "entity_value": entity_value,
            "count":        len(matched),
            "stats":        stats,
            "incidents":    [_row_to_dict(r) for r in matched],
        }

    except Exception as exc:
        logger.error("Failed to fetch entity history for %s=%s: %s", entity_type, entity_value, exc)
        return {"entity_type": entity_type, "entity_value": entity_value, "count": 0, "incidents": [], "stats": {}}