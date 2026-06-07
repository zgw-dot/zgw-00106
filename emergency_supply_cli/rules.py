from datetime import datetime
from typing import List, Tuple, Optional
import sqlite3

from .config import ROLES, STATUS, OPERATION_TYPES
from .database import Database
from .models import MaterialBatch, AllocationRequest


class BusinessException(Exception):
    pass


class PermissionException(BusinessException):
    pass


class StateException(BusinessException):
    pass


class InventoryException(BusinessException):
    pass


class BusinessRules:
    def __init__(self, db: Database = None):
        self.db = db or Database()

    def _check_role(self, operator: str, allowed_roles: List[str]) -> None:
        if operator not in allowed_roles:
            raise PermissionException(
                f"权限不足：用户 '{operator}' 没有权限执行此操作。"
                f"允许的角色：{', '.join(allowed_roles)}"
            )

    def _check_not_terminal(self, request: AllocationRequest, operation: str) -> None:
        if request.is_terminal:
            raise StateException(
                f"无法执行 '{operation}'：申请单 '{request.request_no}' "
                f"当前状态为 '{request.status}'，已处于终态，不可再操作。"
            )

    def _check_available_inventory(
        self, material_name: str, quantity: int, exclude_expired: bool = True
    ) -> Tuple[List[MaterialBatch], int]:
        batches = self.db.get_available_batches(material_name, quantity)
        total_available = sum(b.available_quantity for b in batches)

        if exclude_expired and total_available < quantity:
            all_batches = self.db.list_batches(material_name)
            expired_batches = [b for b in all_batches if b.is_expired]
            if expired_batches:
                raise InventoryException(
                    f"库存不足且存在过期批次：申请 '{material_name}' x{quantity}，"
                    f"有效库存仅 {total_available}，"
                    f"另有 {sum(b.quantity for b in expired_batches)} 已过期不可用。"
                )
            raise InventoryException(
                f"库存不足：申请 '{material_name}' x{quantity}，"
                f"有效库存仅 {total_available}。"
            )

        return batches, total_available

    def create_batch(
        self,
        batch_no: str,
        material_name: str,
        quantity: int,
        expiry_date: str,
        location: str,
        operator: str,
    ) -> MaterialBatch:
        self._check_role(operator, [ROLES["WAREHOUSE_KEEPER"]])

        if quantity <= 0:
            raise BusinessException(f"数量必须大于 0，当前值：{quantity}")

        try:
            datetime.strptime(expiry_date, "%Y-%m-%d")
        except ValueError:
            raise BusinessException(
                f"保质期格式错误：'{expiry_date}'，请使用 YYYY-MM-DD 格式。"
            )

        existing = self.db.get_batch_by_no(batch_no)
        if existing:
            raise BusinessException(f"批次号 '{batch_no}' 已存在，请使用其他批次号。")

        return self.db.create_batch(
            batch_no=batch_no,
            material_name=material_name,
            quantity=quantity,
            expiry_date=expiry_date,
            location=location,
            created_by=operator,
        )

    def create_request(
        self,
        request_no: str,
        material_name: str,
        quantity: int,
        location: str,
        operator: str,
    ) -> AllocationRequest:
        self._check_role(operator, [ROLES["APPLICANT"]])

        if quantity <= 0:
            raise BusinessException(f"申请数量必须大于 0，当前值：{quantity}")

        existing = self.db.get_request_by_no(request_no)
        if existing:
            raise BusinessException(f"申请单号 '{request_no}' 已存在，请使用其他单号。")

        request = self.db.create_request(
            request_no=request_no,
            material_name=material_name,
            quantity=quantity,
            location=location,
            applicant=operator,
        )

        batches, total_available = self._check_available_inventory(
            material_name, quantity, exclude_expired=False
        )

        if total_available < quantity:
            self.db.add_operation_history(
                request_id=request.id,
                batch_id=None,
                operation="inventory_warning",
                operator=operator,
                detail=(
                    f"申请创建时库存预警：{material_name} x{quantity}，"
                    f"当前可用仅 {total_available}，审批时可能因库存不足被拒绝。"
                ),
            )

        return request

    def approve_request(self, request_id: int, operator: str) -> AllocationRequest:
        self._check_role(operator, [ROLES["SUPERVISOR"]])

        request = self.db.get_request(request_id)
        if not request:
            raise BusinessException(f"申请单 ID {request_id} 不存在。")

        self._check_not_terminal(request, "审批")

        if request.status != STATUS["PENDING"]:
            raise StateException(
                f"无法审批：申请单 '{request.request_no}' 当前状态为 '{request.status}'，"
                f"仅待审批（pending）的申请可审批。"
            )

        batches, total_available = self._check_available_inventory(
            request.material_name, request.quantity
        )

        remaining = request.quantity
        allocations = []

        with self.db._get_conn() as conn:
            for batch in batches:
                if remaining <= 0:
                    break
                take = min(batch.available_quantity, remaining)
                self.db.lock_batch_quantity(batch.id, take, conn)
                allocations.append((batch.id, take))
                remaining -= take

            if remaining > 0:
                raise InventoryException(
                    f"库存不足无法审批：申请 '{request.material_name}' x{request.quantity}，"
                    f"锁定后仍缺 {remaining}。"
                )

            request = self.db.update_request_status(
                request_id=request_id,
                status=STATUS["APPROVED"],
                operator=operator,
                conn=conn,
            )

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for batch_id, qty in allocations:
                conn.cursor().execute(
                    """
                    INSERT INTO inventory_logs
                    (batch_id, request_id, change_type, quantity_change, operator, operated_at, remark)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        batch_id,
                        request_id,
                        "lock",
                        0,
                        operator,
                        now,
                        f"审批锁定：申请单 {request.request_no} 锁定 {qty}",
                    ),
                )

            conn.cursor().execute(
                """
                INSERT INTO operation_histories
                (request_id, operation, operator, operated_at, detail)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    OPERATION_TYPES["APPROVE"],
                    operator,
                    now,
                    f"审批通过：{request.material_name} x{request.quantity}，锁定库存。"
                    f"分配批次：{', '.join([f'批次{b}x{q}' for b, q in allocations])}",
                ),
            )

        return request

    def reject_request(self, request_id: int, operator: str, reason: str) -> AllocationRequest:
        self._check_role(operator, [ROLES["SUPERVISOR"]])

        request = self.db.get_request(request_id)
        if not request:
            raise BusinessException(f"申请单 ID {request_id} 不存在。")

        self._check_not_terminal(request, "拒绝")

        if request.status != STATUS["PENDING"]:
            raise StateException(
                f"无法拒绝：申请单 '{request.request_no}' 当前状态为 '{request.status}'，"
                f"仅待审批（pending）的申请可拒绝。"
            )

        request = self.db.update_request_status(
            request_id=request_id,
            status=STATUS["REJECTED"],
            operator=operator,
        )

        self.db.add_operation_history(
            request_id=request_id,
            batch_id=None,
            operation=OPERATION_TYPES["REJECT"],
            operator=operator,
            detail=f"拒绝申请，原因：{reason}",
        )

        return request

    def outbound_request(self, request_id: int, operator: str) -> AllocationRequest:
        self._check_role(operator, [ROLES["WAREHOUSE_KEEPER"]])

        request = self.db.get_request(request_id)
        if not request:
            raise BusinessException(f"申请单 ID {request_id} 不存在。")

        self._check_not_terminal(request, "出库")

        if request.status == STATUS["PENDING"]:
            raise StateException(
                f"无法出库：申请单 '{request.request_no}' 尚未审批，"
                f"请先由主管审批后再出库。"
            )

        if request.status != STATUS["APPROVED"]:
            raise StateException(
                f"无法出库：申请单 '{request.request_no}' 当前状态为 '{request.status}'，"
                f"仅已审批（approved）的申请可出库。"
            )

        logs = self.db.list_inventory_logs(request_id=request_id)
        lock_logs = [l for l in logs if l.change_type == "lock"]
        batch_locks = {}
        for log in lock_logs:
            batch_id = log.batch_id
            if batch_id not in batch_locks:
                batch_locks[batch_id] = 0
            batch = self.db.get_batch(batch_id)
            if batch:
                take = min(batch.locked_quantity, request.quantity - sum(batch_locks.values()))
                if take > 0:
                    batch_locks[batch_id] = take

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db._get_conn() as conn:
            for batch_id, qty in batch_locks.items():
                if qty > 0:
                    self.db.reduce_batch_quantity(batch_id, qty, conn)
                    conn.cursor().execute(
                        """
                        INSERT INTO inventory_logs
                        (batch_id, request_id, change_type, quantity_change, operator, operated_at, remark)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            batch_id,
                            request_id,
                            "outbound",
                            -qty,
                            operator,
                            now,
                            f"出库：申请单 {request.request_no} 出库 {qty}",
                        ),
                    )

            request = self.db.update_request_status(
                request_id=request_id,
                status=STATUS["OUTBOUND"],
                operator=operator,
                conn=conn,
            )

            conn.cursor().execute(
                """
                INSERT INTO operation_histories
                (request_id, operation, operator, operated_at, detail)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    OPERATION_TYPES["OUTBOUND"],
                    operator,
                    now,
                    f"出库完成：{request.material_name} x{request.quantity}",
                ),
            )

        return request

    def partial_return(
        self, request_id: int, quantity: int, operator: str
    ) -> AllocationRequest:
        self._check_role(operator, [ROLES["WAREHOUSE_KEEPER"]])

        request = self.db.get_request(request_id)
        if not request:
            raise BusinessException(f"申请单 ID {request_id} 不存在。")

        self._check_not_terminal(request, "部分归还")

        if request.status not in [STATUS["OUTBOUND"], STATUS["PARTIAL_RETURN"]]:
            raise StateException(
                f"无法归还：申请单 '{request.request_no}' 当前状态为 '{request.status}'，"
                f"仅已出库（outbound）或部分归还（partial_return）的申请可归还。"
            )

        outbound_qty = request.quantity
        returned_qty = request.returned_quantity
        remaining = outbound_qty - returned_qty

        if remaining <= 0:
            raise StateException(
                f"无法归还：申请单 '{request.request_no}' 已全部归还（{returned_qty}/{outbound_qty}），"
                f"请使用全部核销或检查是否重复归还。"
            )

        if quantity <= 0:
            raise BusinessException(f"归还数量必须大于 0，当前值：{quantity}")

        if quantity > remaining:
            raise InventoryException(
                f"超量归还：申请单 '{request.request_no}' 未归还数量为 {remaining}，"
                f"申请归还 {quantity}，超出部分不允许。"
            )

        new_returned = returned_qty + quantity
        new_status = (
            STATUS["FULL_SETTLED"] if new_returned == outbound_qty else STATUS["PARTIAL_RETURN"]
        )

        logs = self.db.list_inventory_logs(request_id=request_id)
        outbound_logs = [l for l in logs if l.change_type == "outbound"]

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db._get_conn() as conn:
            return_qty_left = quantity
            for log in outbound_logs:
                if return_qty_left <= 0:
                    break
                batch_id = log.batch_id
                return_qty = min(abs(log.quantity_change), return_qty_left)
                self.db.increase_batch_quantity(batch_id, return_qty, conn)
                return_qty_left -= return_qty

                conn.cursor().execute(
                    """
                    INSERT INTO inventory_logs
                    (batch_id, request_id, change_type, quantity_change, operator, operated_at, remark)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        batch_id,
                        request_id,
                        "return",
                        return_qty,
                        operator,
                        now,
                        f"归还：申请单 {request.request_no} 归还 {return_qty}",
                    ),
                )

            request = self.db.update_request_status(
                request_id=request_id,
                status=new_status,
                operator=operator,
                extra_fields={"returned_quantity": new_returned},
                conn=conn,
            )

            conn.cursor().execute(
                """
                INSERT INTO operation_histories
                (request_id, operation, operator, operated_at, detail)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    OPERATION_TYPES["PARTIAL_RETURN"],
                    operator,
                    now,
                    f"部分归还：{request.material_name} x{quantity}，"
                    f"累计归还 {new_returned}/{outbound_qty}，"
                    f"状态变更为 {new_status}",
                ),
            )

        return request

    def full_settle(self, request_id: int, operator: str) -> AllocationRequest:
        self._check_role(operator, [ROLES["WAREHOUSE_KEEPER"]])

        request = self.db.get_request(request_id)
        if not request:
            raise BusinessException(f"申请单 ID {request_id} 不存在。")

        self._check_not_terminal(request, "全部核销")

        if request.status not in [STATUS["OUTBOUND"], STATUS["PARTIAL_RETURN"]]:
            raise StateException(
                f"无法核销：申请单 '{request.request_no}' 当前状态为 '{request.status}'，"
                f"仅已出库（outbound）或部分归还（partial_return）的申请可核销。"
            )

        request = self.db.update_request_status(
            request_id=request_id,
            status=STATUS["FULL_SETTLED"],
            operator=operator,
            extra_fields={"returned_quantity": request.quantity},
        )

        self.db.add_operation_history(
            request_id=request_id,
            batch_id=None,
            operation=OPERATION_TYPES["FULL_SETTLE"],
            operator=operator,
            detail=(
                f"全部核销：{request.material_name} x{request.quantity}，"
                f"已归还 {request.returned_quantity}，"
                f"核销 {request.quantity - request.returned_quantity}。"
            ),
        )

        return request

    def cancel_request(self, request_id: int, operator: str) -> AllocationRequest:
        self._check_role(operator, [ROLES["APPLICANT"]])

        request = self.db.get_request(request_id)
        if not request:
            raise BusinessException(f"申请单 ID {request_id} 不存在。")

        self._check_not_terminal(request, "取消")

        if request.applicant != operator:
            raise PermissionException(
                f"无法取消：申请单 '{request.request_no}' 的申请人是 '{request.applicant}'，"
                f"仅申请人本人可取消。"
            )

        if request.status not in [STATUS["PENDING"], STATUS["APPROVED"]]:
            raise StateException(
                f"无法取消：申请单 '{request.request_no}' 当前状态为 '{request.status}'，"
                f"仅待审批（pending）或已审批（approved）的申请可取消。"
            )

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if request.status == STATUS["APPROVED"]:
            logs = self.db.list_inventory_logs(request_id=request_id)
            lock_logs = [l for l in logs if l.change_type == "lock"]
            batch_data = []
            for log in lock_logs:
                batch = self.db.get_batch(log.batch_id)
                if batch and batch.locked_quantity > 0:
                    unlock_qty = min(batch.locked_quantity, request.quantity)
                    if unlock_qty > 0:
                        batch_data.append((log.batch_id, unlock_qty))

            with self.db._get_conn() as conn:
                for batch_id, unlock_qty in batch_data:
                    self.db.unlock_batch_quantity(batch_id, unlock_qty, conn)
                    conn.cursor().execute(
                        """
                        INSERT INTO inventory_logs
                        (batch_id, request_id, change_type, quantity_change, operator, operated_at, remark)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            batch_id,
                            request_id,
                            "unlock",
                            0,
                            operator,
                            now,
                            f"取消解锁：申请单 {request.request_no} 解锁 {unlock_qty}",
                        ),
                    )

                request = self.db.update_request_status(
                    request_id=request_id,
                    status=STATUS["CANCELLED"],
                    operator=operator,
                    conn=conn,
                )

                conn.cursor().execute(
                    """
                    INSERT INTO operation_histories
                    (request_id, operation, operator, operated_at, detail)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        request_id,
                        OPERATION_TYPES["CANCEL"],
                        operator,
                        now,
                        f"申请人取消申请，状态变更为 cancelled。",
                    ),
                )
        else:
            request = self.db.update_request_status(
                request_id=request_id,
                status=STATUS["CANCELLED"],
                operator=operator,
            )
            self.db.add_operation_history(
                request_id=request_id,
                batch_id=None,
                operation=OPERATION_TYPES["CANCEL"],
                operator=operator,
                detail=f"申请人取消待审批申请。",
            )

        return request

    def revert_request(
        self, request_id: int, reason: str, operator: str
    ) -> AllocationRequest:
        self._check_role(operator, [ROLES["SUPERVISOR"]])

        if not reason or len(reason.strip()) == 0:
            raise BusinessException("撤销更正必须提供原因说明。")

        request = self.db.get_request(request_id)
        if not request:
            raise BusinessException(f"申请单 ID {request_id} 不存在。")

        if request.status == STATUS["REVERTED"]:
            raise StateException(
                f"无法撤销：申请单 '{request.request_no}' 已处于撤销更正状态。"
            )

        valid_states = [
            STATUS["APPROVED"],
            STATUS["OUTBOUND"],
            STATUS["PARTIAL_RETURN"],
            STATUS["FULL_SETTLED"],
            STATUS["CANCELLED"],
        ]

        if request.status not in valid_states:
            raise StateException(
                f"无法撤销：申请单 '{request.request_no}' 当前状态为 '{request.status}'，"
                f"仅以下状态可撤销更正：{', '.join(valid_states)}。"
            )

        logs = self.db.list_inventory_logs(request_id=request_id)

        restore_data = []
        unlock_data = []
        for log in logs:
            if log.change_type == "outbound":
                restore_qty = abs(log.quantity_change)
                restore_data.append((log.batch_id, restore_qty))
            elif log.change_type == "lock":
                batch = self.db.get_batch(log.batch_id)
                if batch and batch.locked_quantity > 0:
                    unlock_qty = min(batch.locked_quantity, request.quantity)
                    if unlock_qty > 0:
                        unlock_data.append((log.batch_id, unlock_qty))

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db._get_conn() as conn:
            for batch_id, restore_qty in restore_data:
                self.db.increase_batch_quantity(batch_id, restore_qty, conn)
                conn.cursor().execute(
                    """
                    INSERT INTO inventory_logs
                    (batch_id, request_id, change_type, quantity_change, operator, operated_at, remark)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        batch_id,
                        request_id,
                        "revert_restore",
                        restore_qty,
                        operator,
                        now,
                        f"撤销更正恢复：申请单 {request.request_no} 恢复 {restore_qty}",
                    ),
                )

            for batch_id, unlock_qty in unlock_data:
                self.db.unlock_batch_quantity(batch_id, unlock_qty, conn)

            request = self.db.update_request_status(
                request_id=request_id,
                status=STATUS["REVERTED"],
                operator=operator,
                extra_fields={"revert_reason": reason},
                conn=conn,
            )

            conn.cursor().execute(
                """
                INSERT INTO operation_histories
                (request_id, operation, operator, operated_at, detail)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    OPERATION_TYPES["REVERT"],
                    operator,
                    now,
                    f"撤销更正：原因：{reason}。状态变更为 reverted，库存已恢复。",
                ),
            )

        return request
