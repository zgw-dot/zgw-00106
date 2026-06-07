import os
from pathlib import Path

BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent
DB_PATH = BASE_DIR / "data" / "emergency_supply.db"

ROLES = {
    "WAREHOUSE_KEEPER": "warehouse_keeper",
    "APPLICANT": "applicant",
    "SUPERVISOR": "supervisor",
}

STATUS = {
    "PENDING": "pending",
    "APPROVED": "approved",
    "REJECTED": "rejected",
    "OUTBOUND": "outbound",
    "PARTIAL_RETURN": "partial_return",
    "FULL_SETTLED": "full_settled",
    "CANCELLED": "cancelled",
    "REVERTED": "reverted",
}

OPERATION_TYPES = {
    "CREATE_BATCH": "create_batch",
    "CREATE_REQUEST": "create_request",
    "APPROVE": "approve",
    "REJECT": "reject",
    "OUTBOUND": "outbound",
    "PARTIAL_RETURN": "partial_return",
    "FULL_SETTLE": "full_settle",
    "CANCEL": "cancel",
    "REVERT": "revert",
}

DB_PATH.parent.mkdir(parents=True, exist_ok=True)
