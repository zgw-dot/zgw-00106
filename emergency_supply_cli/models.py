from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from .config import STATUS, ROLES


@dataclass
class MaterialBatch:
    id: Optional[int]
    batch_no: str
    material_name: str
    quantity: int
    expiry_date: str
    location: str
    created_by: str
    created_at: str
    locked_quantity: int = 0
    is_active: int = 1

    @property
    def available_quantity(self) -> int:
        return self.quantity - self.locked_quantity

    @property
    def is_expired(self) -> bool:
        today = datetime.now().strftime("%Y-%m-%d")
        return self.expiry_date < today


@dataclass
class AllocationRequest:
    id: Optional[int]
    request_no: str
    material_name: str
    quantity: int
    location: str
    applicant: str
    status: str
    created_at: str
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None
    outbound_at: Optional[str] = None
    outbound_by: Optional[str] = None
    returned_quantity: int = 0
    cancelled_at: Optional[str] = None
    cancelled_by: Optional[str] = None
    revert_reason: Optional[str] = None
    reverted_at: Optional[str] = None
    reverted_by: Optional[str] = None

    @property
    def is_terminal(self) -> bool:
        return self.status in [
            STATUS["REJECTED"],
            STATUS["FULL_SETTLED"],
            STATUS["CANCELLED"],
            STATUS["REVERTED"],
        ]


@dataclass
class InventoryLog:
    id: Optional[int]
    batch_id: int
    request_id: Optional[int]
    change_type: str
    quantity_change: int
    operator: str
    operated_at: str
    remark: str


@dataclass
class OperationHistory:
    id: Optional[int]
    request_id: Optional[int]
    batch_id: Optional[int]
    operation: str
    operator: str
    operated_at: str
    detail: str


@dataclass
class AuditAnomaly:
    anomaly_type: str
    severity: str
    material_name: Optional[str]
    entity_id: Optional[int]
    entity_no: Optional[str]
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BatchSummary:
    batch_id: int
    batch_no: str
    quantity: int
    locked_quantity: int
    available_quantity: int
    expiry_date: str
    location: str
    created_at: str
    is_expired: bool


@dataclass
class RequestSummary:
    request_id: int
    request_no: str
    quantity: int
    status: str
    returned_quantity: int
    created_at: str
    applicant: str
    log_count: int


@dataclass
class MaterialAudit:
    material_name: str
    total_quantity: int
    total_locked: int
    total_available: int
    batches: List[BatchSummary]
    requests: List[RequestSummary]
    log_count: int
    operation_count: int


@dataclass
class AuditSnapshot:
    snapshot_at: str
    operator: str
    operator_role: str
    filters: Dict[str, Any]
    materials: List[MaterialAudit]
    anomalies: List[AuditAnomaly]
    summary: Dict[str, Any]
