from dataclasses import dataclass
from datetime import datetime
from typing import Optional
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
