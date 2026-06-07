import json
import csv
from dataclasses import asdict
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

from .database import Database
from .rules import BusinessException
from .models import AuditSnapshot


class DataIO:
    def __init__(self, db: Database = None):
        self.db = db or Database()

    def export_data(self, output_path: str, format_type: str = "json") -> str:
        format_type = format_type.lower()
        if format_type not in ["json", "csv"]:
            raise BusinessException(f"不支持的导出格式：{format_type}，请使用 json 或 csv。")

        data = {
            "export_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "material_batches": self.db.get_all_batches_for_export(),
            "allocation_requests": self.db.get_all_requests_for_export(),
            "inventory_logs": self.db.get_all_logs_for_export(),
            "operation_histories": self.db.get_all_histories_for_export(),
        }

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if format_type == "json":
            if not output_path.suffix:
                output_path = output_path.with_suffix(".json")
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        else:
            if not output_path.suffix:
                output_path = output_path.with_suffix(".csv")
            self._export_to_csv(data, output_path)

        return str(output_path)

    def _export_to_csv(self, data: Dict[str, Any], base_path: Path) -> None:
        base_name = base_path.stem
        csv_files = {
            f"{base_name}_material_batches.csv": data["material_batches"],
            f"{base_name}_allocation_requests.csv": data["allocation_requests"],
            f"{base_name}_inventory_logs.csv": data["inventory_logs"],
            f"{base_name}_operation_histories.csv": data["operation_histories"],
        }

        for filename, rows in csv_files.items():
            filepath = base_path.parent / filename
            if rows:
                fieldnames = list(rows[0].keys())
                with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
            else:
                with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                    f.write("")

    def import_data(self, input_path: str, format_type: str = "json") -> Dict[str, int]:
        format_type = format_type.lower()
        if format_type not in ["json", "csv"]:
            raise BusinessException(f"不支持的导入格式：{format_type}，请使用 json 或 csv。")

        input_path = Path(input_path)
        if not input_path.exists():
            raise BusinessException(f"导入文件不存在：{input_path}")

        if format_type == "json":
            return self._import_from_json(input_path)
        else:
            return self._import_from_csv(input_path)

    def _import_from_json(self, input_path: Path) -> Dict[str, int]:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return self._load_data(data)

    def _import_from_csv(self, input_path: Path) -> Dict[str, int]:
        base_name = input_path.stem
        csv_files = {
            "material_batches": f"{base_name}_material_batches.csv",
            "allocation_requests": f"{base_name}_allocation_requests.csv",
            "inventory_logs": f"{base_name}_inventory_logs.csv",
            "operation_histories": f"{base_name}_operation_histories.csv",
        }

        data = {}
        for key, filename in csv_files.items():
            filepath = input_path.parent / filename
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    data[key] = [self._convert_csv_types(row) for row in reader]
            else:
                data[key] = []

        return self._load_data(data)

    def _convert_csv_types(self, row: Dict[str, str]) -> Dict[str, Any]:
        int_fields = [
            "id",
            "quantity",
            "locked_quantity",
            "is_active",
            "quantity_change",
            "returned_quantity",
            "batch_id",
            "request_id",
        ]
        for field in int_fields:
            if field in row and row[field] != "" and row[field] is not None:
                try:
                    row[field] = int(row[field])
                except (ValueError, TypeError):
                    row[field] = None if field in ["id", "request_id", "batch_id"] else 0
            elif field in row and (row[field] == "" or row[field] is None):
                if field in ["id", "request_id", "batch_id"]:
                    row[field] = None
                else:
                    row[field] = 0
        return row

    def _load_data(self, data: Dict[str, Any]) -> Dict[str, int]:
        counts = {"batches": 0, "requests": 0, "logs": 0, "histories": 0}

        with self.db._get_conn() as conn:
            c = conn.cursor()

            for batch in data.get("material_batches", []):
                if "id" in batch and batch["id"] is not None:
                    del batch["id"]
                try:
                    c.execute(
                        """
                        INSERT OR IGNORE INTO material_batches
                        (batch_no, material_name, quantity, locked_quantity, expiry_date,
                         location, created_by, created_at, is_active)
                        VALUES (:batch_no, :material_name, :quantity, :locked_quantity,
                                :expiry_date, :location, :created_by, :created_at, :is_active)
                        """,
                        batch,
                    )
                    if c.rowcount > 0:
                        counts["batches"] += 1
                except Exception:
                    continue

            for request in data.get("allocation_requests", []):
                if "id" in request and request["id"] is not None:
                    del request["id"]
                try:
                    c.execute(
                        """
                        INSERT OR IGNORE INTO allocation_requests
                        (request_no, material_name, quantity, location, applicant, status,
                         created_at, approved_at, approved_by, outbound_at, outbound_by,
                         returned_quantity, cancelled_at, cancelled_by, revert_reason,
                         reverted_at, reverted_by)
                        VALUES (:request_no, :material_name, :quantity, :location, :applicant,
                                :status, :created_at, :approved_at, :approved_by,
                                :outbound_at, :outbound_by, :returned_quantity,
                                :cancelled_at, :cancelled_by, :revert_reason,
                                :reverted_at, :reverted_by)
                        """,
                        request,
                    )
                    if c.rowcount > 0:
                        counts["requests"] += 1
                except Exception:
                    continue

            for log in data.get("inventory_logs", []):
                if "id" in log and log["id"] is not None:
                    del log["id"]
                try:
                    c.execute(
                        """
                        INSERT OR IGNORE INTO inventory_logs
                        (batch_id, request_id, change_type, quantity_change, operator,
                         operated_at, remark)
                        VALUES (:batch_id, :request_id, :change_type, :quantity_change,
                                :operator, :operated_at, :remark)
                        """,
                        log,
                    )
                    if c.rowcount > 0:
                        counts["logs"] += 1
                except Exception:
                    continue

            for history in data.get("operation_histories", []):
                if "id" in history and history["id"] is not None:
                    del history["id"]
                try:
                    c.execute(
                        """
                        INSERT OR IGNORE INTO operation_histories
                        (request_id, batch_id, operation, operator, operated_at, detail)
                        VALUES (:request_id, :batch_id, :operation, :operator,
                                :operated_at, :detail)
                        """,
                        history,
                    )
                    if c.rowcount > 0:
                        counts["histories"] += 1
                except Exception:
                    continue

        return counts

    def export_audit_snapshot(
        self, snapshot: AuditSnapshot, output_path: str, format_type: str = "json"
    ) -> str:
        format_type = format_type.lower()
        if format_type not in ["json", "csv"]:
            raise BusinessException(f"不支持的导出格式：{format_type}，请使用 json 或 csv。")

        snapshot_dict = self._snapshot_to_dict(snapshot)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if format_type == "json":
            if not output_path.suffix:
                output_path = output_path.with_suffix(".json")
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(snapshot_dict, f, ensure_ascii=False, indent=2)
        else:
            if not output_path.suffix:
                output_path = output_path.with_suffix("")
            self._export_snapshot_to_csv(snapshot_dict, output_path)

        return str(output_path)

    def _snapshot_to_dict(self, snapshot: AuditSnapshot) -> Dict[str, Any]:
        return {
            "snapshot_at": snapshot.snapshot_at,
            "operator": snapshot.operator,
            "operator_role": snapshot.operator_role,
            "filters": snapshot.filters,
            "summary": snapshot.summary,
            "materials": [
                {
                    "material_name": m.material_name,
                    "total_quantity": m.total_quantity,
                    "total_locked": m.total_locked,
                    "total_available": m.total_available,
                    "log_count": m.log_count,
                    "operation_count": m.operation_count,
                    "batches": [asdict(b) for b in m.batches],
                    "requests": [asdict(r) for r in m.requests],
                }
                for m in snapshot.materials
            ],
            "anomalies": [asdict(a) for a in snapshot.anomalies],
        }

    def _export_snapshot_to_csv(
        self, snapshot_dict: Dict[str, Any], base_path: Path
    ) -> None:
        base_name = base_path.stem if base_path.suffix else base_path.name

        with open(f"{base_path}_summary.csv", "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["项目", "数值"])
            for key, value in snapshot_dict["summary"].items():
                writer.writerow([key, value])
            writer.writerow(["snapshot_at", snapshot_dict["snapshot_at"]])
            writer.writerow(["operator", snapshot_dict["operator"]])
            writer.writerow(["operator_role", snapshot_dict["operator_role"]])
            writer.writerow(["filter_material", snapshot_dict["filters"]["material_name"]])
            writer.writerow(["filter_start_time", snapshot_dict["filters"]["start_time"]])
            writer.writerow(["filter_end_time", snapshot_dict["filters"]["end_time"]])

        if snapshot_dict["materials"]:
            material_fieldnames = [
                "material_name", "total_quantity", "total_locked",
                "total_available", "batch_count", "request_count",
                "log_count", "operation_count"
            ]
            with open(f"{base_path}_materials.csv", "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=material_fieldnames)
                writer.writeheader()
                for m in snapshot_dict["materials"]:
                    writer.writerow({
                        "material_name": m["material_name"],
                        "total_quantity": m["total_quantity"],
                        "total_locked": m["total_locked"],
                        "total_available": m["total_available"],
                        "batch_count": len(m["batches"]),
                        "request_count": len(m["requests"]),
                        "log_count": m["log_count"],
                        "operation_count": m["operation_count"],
                    })

            batch_fieldnames = [
                "material_name", "batch_id", "batch_no", "quantity",
                "locked_quantity", "available_quantity",
                "expiry_date", "location", "created_at", "is_expired"
            ]
            with open(f"{base_path}_batches.csv", "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=batch_fieldnames)
                writer.writeheader()
                for m in snapshot_dict["materials"]:
                    for b in m["batches"]:
                        row = dict(b)
                        row["material_name"] = m["material_name"]
                        writer.writerow(row)

            request_fieldnames = [
                "material_name", "request_id", "request_no", "quantity",
                "status", "returned_quantity", "created_at", "applicant", "log_count"
            ]
            with open(f"{base_path}_requests.csv", "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=request_fieldnames)
                writer.writeheader()
                for m in snapshot_dict["materials"]:
                    for r in m["requests"]:
                        row = dict(r)
                        row["material_name"] = m["material_name"]
                        writer.writerow(row)

        if snapshot_dict["anomalies"]:
            anomaly_fieldnames = [
                "anomaly_type", "severity", "material_name",
                "entity_id", "entity_no", "message", "details"
            ]
            with open(f"{base_path}_anomalies.csv", "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=anomaly_fieldnames)
                writer.writeheader()
                for a in snapshot_dict["anomalies"]:
                    row = dict(a)
                    row["details"] = json.dumps(a["details"], ensure_ascii=False)
                    writer.writerow(row)
