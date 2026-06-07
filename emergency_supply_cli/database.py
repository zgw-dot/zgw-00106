import sqlite3
from datetime import datetime
from typing import List, Optional, Tuple
from contextlib import contextmanager

from .config import DB_PATH, STATUS, OPERATION_TYPES
from .models import MaterialBatch, AllocationRequest, InventoryLog, OperationHistory


class Database:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        self._init_db()

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self._get_conn() as conn:
            c = conn.cursor()
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS material_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_no TEXT UNIQUE NOT NULL,
                    material_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    locked_quantity INTEGER DEFAULT 0,
                    expiry_date TEXT NOT NULL,
                    location TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS allocation_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_no TEXT UNIQUE NOT NULL,
                    material_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    location TEXT NOT NULL,
                    applicant TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    approved_at TEXT,
                    approved_by TEXT,
                    outbound_at TEXT,
                    outbound_by TEXT,
                    returned_quantity INTEGER DEFAULT 0,
                    cancelled_at TEXT,
                    cancelled_by TEXT,
                    revert_reason TEXT,
                    reverted_at TEXT,
                    reverted_by TEXT
                );

                CREATE TABLE IF NOT EXISTS inventory_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id INTEGER NOT NULL,
                    request_id INTEGER,
                    change_type TEXT NOT NULL,
                    quantity_change INTEGER NOT NULL,
                    operator TEXT NOT NULL,
                    operated_at TEXT NOT NULL,
                    remark TEXT,
                    FOREIGN KEY (batch_id) REFERENCES material_batches(id),
                    FOREIGN KEY (request_id) REFERENCES allocation_requests(id)
                );

                CREATE TABLE IF NOT EXISTS operation_histories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id INTEGER,
                    batch_id INTEGER,
                    operation TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    operated_at TEXT NOT NULL,
                    detail TEXT,
                    FOREIGN KEY (request_id) REFERENCES allocation_requests(id),
                    FOREIGN KEY (batch_id) REFERENCES material_batches(id)
                );
                """
            )

    def _row_to_batch(self, row: sqlite3.Row) -> MaterialBatch:
        return MaterialBatch(
            id=row["id"],
            batch_no=row["batch_no"],
            material_name=row["material_name"],
            quantity=row["quantity"],
            locked_quantity=row["locked_quantity"],
            expiry_date=row["expiry_date"],
            location=row["location"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            is_active=row["is_active"],
        )

    def _row_to_request(self, row: sqlite3.Row) -> AllocationRequest:
        return AllocationRequest(
            id=row["id"],
            request_no=row["request_no"],
            material_name=row["material_name"],
            quantity=row["quantity"],
            location=row["location"],
            applicant=row["applicant"],
            status=row["status"],
            created_at=row["created_at"],
            approved_at=row["approved_at"],
            approved_by=row["approved_by"],
            outbound_at=row["outbound_at"],
            outbound_by=row["outbound_by"],
            returned_quantity=row["returned_quantity"],
            cancelled_at=row["cancelled_at"],
            cancelled_by=row["cancelled_by"],
            revert_reason=row["revert_reason"],
            reverted_at=row["reverted_at"],
            reverted_by=row["reverted_by"],
        )

    def _row_to_log(self, row: sqlite3.Row) -> InventoryLog:
        return InventoryLog(
            id=row["id"],
            batch_id=row["batch_id"],
            request_id=row["request_id"],
            change_type=row["change_type"],
            quantity_change=row["quantity_change"],
            operator=row["operator"],
            operated_at=row["operated_at"],
            remark=row["remark"],
        )

    def _row_to_history(self, row: sqlite3.Row) -> OperationHistory:
        return OperationHistory(
            id=row["id"],
            request_id=row["request_id"],
            batch_id=row["batch_id"],
            operation=row["operation"],
            operator=row["operator"],
            operated_at=row["operated_at"],
            detail=row["detail"],
        )

    def create_batch(
        self,
        batch_no: str,
        material_name: str,
        quantity: int,
        expiry_date: str,
        location: str,
        created_by: str,
    ) -> MaterialBatch:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                """
                INSERT INTO material_batches
                (batch_no, material_name, quantity, expiry_date, location, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (batch_no, material_name, quantity, expiry_date, location, created_by, now),
            )
            batch_id = c.lastrowid
            c.execute(
                """
                INSERT INTO operation_histories
                (batch_id, operation, operator, operated_at, detail)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    OPERATION_TYPES["CREATE_BATCH"],
                    created_by,
                    now,
                    f"Created batch {batch_no}: {material_name} x{quantity}, expiry {expiry_date}, location {location}",
                ),
            )
            c.execute("SELECT * FROM material_batches WHERE id = ?", (batch_id,))
            return self._row_to_batch(c.fetchone())

    def get_batch(self, batch_id: int) -> Optional[MaterialBatch]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM material_batches WHERE id = ? AND is_active = 1", (batch_id,))
            row = c.fetchone()
            return self._row_to_batch(row) if row else None

    def get_batch_by_no(self, batch_no: str) -> Optional[MaterialBatch]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM material_batches WHERE batch_no = ? AND is_active = 1", (batch_no,))
            row = c.fetchone()
            return self._row_to_batch(row) if row else None

    def list_batches(self, material_name: str = None) -> List[MaterialBatch]:
        with self._get_conn() as conn:
            c = conn.cursor()
            if material_name:
                c.execute(
                    "SELECT * FROM material_batches WHERE is_active = 1 AND material_name = ? ORDER BY created_at DESC",
                    (material_name,),
                )
            else:
                c.execute(
                    "SELECT * FROM material_batches WHERE is_active = 1 ORDER BY created_at DESC"
                )
            return [self._row_to_batch(row) for row in c.fetchall()]

    def get_available_batches(self, material_name: str, quantity: int) -> List[MaterialBatch]:
        with self._get_conn() as conn:
            c = conn.cursor()
            today = datetime.now().strftime("%Y-%m-%d")
            c.execute(
                """
                SELECT * FROM material_batches
                WHERE is_active = 1
                  AND material_name = ?
                  AND (quantity - locked_quantity) > 0
                  AND expiry_date >= ?
                ORDER BY expiry_date ASC
                """,
                (material_name, today),
            )
            return [self._row_to_batch(row) for row in c.fetchall()]

    def lock_batch_quantity(self, batch_id: int, quantity: int, conn: sqlite3.Connection):
        c = conn.cursor()
        c.execute(
            "UPDATE material_batches SET locked_quantity = locked_quantity + ? WHERE id = ?",
            (quantity, batch_id),
        )

    def unlock_batch_quantity(self, batch_id: int, quantity: int, conn: sqlite3.Connection):
        c = conn.cursor()
        c.execute(
            "UPDATE material_batches SET locked_quantity = locked_quantity - ? WHERE id = ?",
            (quantity, batch_id),
        )

    def reduce_batch_quantity(self, batch_id: int, quantity: int, conn: sqlite3.Connection):
        c = conn.cursor()
        c.execute(
            "UPDATE material_batches SET quantity = quantity - ?, locked_quantity = locked_quantity - ? WHERE id = ?",
            (quantity, quantity, batch_id),
        )

    def increase_batch_quantity(self, batch_id: int, quantity: int, conn: sqlite3.Connection):
        c = conn.cursor()
        c.execute(
            "UPDATE material_batches SET quantity = quantity + ? WHERE id = ?",
            (quantity, batch_id),
        )

    def create_request(
        self,
        request_no: str,
        material_name: str,
        quantity: int,
        location: str,
        applicant: str,
    ) -> AllocationRequest:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                """
                INSERT INTO allocation_requests
                (request_no, material_name, quantity, location, applicant, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (request_no, material_name, quantity, location, applicant, STATUS["PENDING"], now),
            )
            request_id = c.lastrowid
            c.execute(
                """
                INSERT INTO operation_histories
                (request_id, operation, operator, operated_at, detail)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    OPERATION_TYPES["CREATE_REQUEST"],
                    applicant,
                    now,
                    f"Created request {request_no}: {material_name} x{quantity} for {location}",
                ),
            )
            c.execute("SELECT * FROM allocation_requests WHERE id = ?", (request_id,))
            return self._row_to_request(c.fetchone())

    def get_request(self, request_id: int) -> Optional[AllocationRequest]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM allocation_requests WHERE id = ?", (request_id,))
            row = c.fetchone()
            return self._row_to_request(row) if row else None

    def get_request_by_no(self, request_no: str) -> Optional[AllocationRequest]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM allocation_requests WHERE request_no = ?", (request_no,))
            row = c.fetchone()
            return self._row_to_request(row) if row else None

    def list_requests(self, status: str = None) -> List[AllocationRequest]:
        with self._get_conn() as conn:
            c = conn.cursor()
            if status:
                c.execute(
                    "SELECT * FROM allocation_requests WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                )
            else:
                c.execute("SELECT * FROM allocation_requests ORDER BY created_at DESC")
            return [self._row_to_request(row) for row in c.fetchall()]

    def update_request_status(
        self,
        request_id: int,
        status: str,
        operator: str,
        extra_fields: dict = None,
        conn: sqlite3.Connection = None,
    ) -> AllocationRequest:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        def _do_update(c):
            set_clauses = ["status = ?"]
            params = [status]

            if status == STATUS["APPROVED"]:
                set_clauses.append("approved_at = ?")
                set_clauses.append("approved_by = ?")
                params.extend([now, operator])
            elif status == STATUS["OUTBOUND"]:
                set_clauses.append("outbound_at = ?")
                set_clauses.append("outbound_by = ?")
                params.extend([now, operator])
            elif status == STATUS["CANCELLED"]:
                set_clauses.append("cancelled_at = ?")
                set_clauses.append("cancelled_by = ?")
                params.extend([now, operator])
            elif status == STATUS["REVERTED"]:
                set_clauses.append("reverted_at = ?")
                set_clauses.append("reverted_by = ?")
                if extra_fields and "revert_reason" in extra_fields:
                    set_clauses.append("revert_reason = ?")
                    params.extend([now, operator, extra_fields["revert_reason"]])
                else:
                    params.extend([now, operator])

            if extra_fields and "returned_quantity" in extra_fields:
                set_clauses.append("returned_quantity = ?")
                params.append(extra_fields["returned_quantity"])

            params.append(request_id)
            c.execute(
                f"UPDATE allocation_requests SET {', '.join(set_clauses)} WHERE id = ?",
                params,
            )
            c.execute("SELECT * FROM allocation_requests WHERE id = ?", (request_id,))
            return self._row_to_request(c.fetchone())

        if conn:
            return _do_update(conn.cursor())
        else:
            with self._get_conn() as _conn:
                return _do_update(_conn.cursor())

    def add_inventory_log(
        self,
        batch_id: int,
        request_id: Optional[int],
        change_type: str,
        quantity_change: int,
        operator: str,
        remark: str,
    ) -> InventoryLog:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                """
                INSERT INTO inventory_logs
                (batch_id, request_id, change_type, quantity_change, operator, operated_at, remark)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (batch_id, request_id, change_type, quantity_change, operator, now, remark),
            )
            log_id = c.lastrowid
            c.execute("SELECT * FROM inventory_logs WHERE id = ?", (log_id,))
            return self._row_to_log(c.fetchone())

    def add_operation_history(
        self,
        request_id: Optional[int],
        batch_id: Optional[int],
        operation: str,
        operator: str,
        detail: str,
    ) -> OperationHistory:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute(
                """
                INSERT INTO operation_histories
                (request_id, batch_id, operation, operator, operated_at, detail)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (request_id, batch_id, operation, operator, now, detail),
            )
            history_id = c.lastrowid
            c.execute("SELECT * FROM operation_histories WHERE id = ?", (history_id,))
            return self._row_to_history(c.fetchone())

    def list_inventory_logs(self, batch_id: int = None, request_id: int = None) -> List[InventoryLog]:
        with self._get_conn() as conn:
            c = conn.cursor()
            query = "SELECT * FROM inventory_logs WHERE 1=1"
            params = []
            if batch_id:
                query += " AND batch_id = ?"
                params.append(batch_id)
            if request_id:
                query += " AND request_id = ?"
                params.append(request_id)
            query += " ORDER BY operated_at DESC"
            c.execute(query, params)
            return [self._row_to_log(row) for row in c.fetchall()]

    def list_operation_histories(
        self, request_id: int = None, batch_id: int = None
    ) -> List[OperationHistory]:
        with self._get_conn() as conn:
            c = conn.cursor()
            query = "SELECT * FROM operation_histories WHERE 1=1"
            params = []
            if request_id:
                query += " AND request_id = ?"
                params.append(request_id)
            if batch_id:
                query += " AND batch_id = ?"
                params.append(batch_id)
            query += " ORDER BY operated_at DESC"
            c.execute(query, params)
            return [self._row_to_history(row) for row in c.fetchall()]

    def get_all_batches_for_export(self) -> List[dict]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM material_batches ORDER BY created_at DESC")
            return [dict(row) for row in c.fetchall()]

    def get_all_requests_for_export(self) -> List[dict]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM allocation_requests ORDER BY created_at DESC")
            return [dict(row) for row in c.fetchall()]

    def get_all_logs_for_export(self) -> List[dict]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM inventory_logs ORDER BY operated_at DESC")
            return [dict(row) for row in c.fetchall()]

    def get_all_histories_for_export(self) -> List[dict]:
        with self._get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM operation_histories ORDER BY operated_at DESC")
            return [dict(row) for row in c.fetchall()]
