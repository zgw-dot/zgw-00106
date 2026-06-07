import argparse
import sys
from typing import List

from .config import ROLES, STATUS, OPERATION_TYPES
from .database import Database
from .rules import (
    BusinessRules,
    BusinessException,
    PermissionException,
    StateException,
    InventoryException,
)
from .io import DataIO
from .models import MaterialBatch, AllocationRequest, InventoryLog, OperationHistory


class CLI:
    def __init__(self):
        self.db = Database()
        self.rules = BusinessRules(self.db)
        self.io = DataIO(self.db)

    def run(self):
        parser = self._build_parser()
        args = parser.parse_args()

        if hasattr(args, "func"):
            try:
                args.func(args)
            except PermissionException as e:
                print(f"[权限错误] {e}", file=sys.stderr)
                sys.exit(2)
            except StateException as e:
                print(f"[状态错误] {e}", file=sys.stderr)
                sys.exit(3)
            except InventoryException as e:
                print(f"[库存错误] {e}", file=sys.stderr)
                sys.exit(4)
            except BusinessException as e:
                print(f"[业务错误] {e}", file=sys.stderr)
                sys.exit(1)
            except Exception as e:
                print(f"[系统错误] {e}", file=sys.stderr)
                sys.exit(99)
        else:
            parser.print_help()

    def _build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog="emergency-supply",
            description="社区应急物资调拨管理系统 CLI",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
角色说明：
  warehouse_keeper  仓管：录入物资批次、出库、归还、核销
  applicant         申请人：提交调拨申请、取消申请
  supervisor        主管：审批申请、拒绝申请、撤销更正

状态流转：
  pending(待审批) → approved(已审批) → outbound(已出库) → partial_return(部分归还)
                                                           ↘ full_settled(全部核销)
                  ↘ rejected(已拒绝)
                  ↘ cancelled(已取消) [申请人]
  所有已处理状态 → reverted(已撤销) [主管]
            """,
        )
        subparsers = parser.add_subparsers(dest="command", title="可用命令")

        self._add_batch_commands(subparsers)
        self._add_request_commands(subparsers)
        self._add_query_commands(subparsers)
        self._add_io_commands(subparsers)

        return parser

    def _add_batch_commands(self, subparsers):
        batch_parser = subparsers.add_parser(
            "create-batch", help="仓管录入物资批次", aliases=["cb"]
        )
        batch_parser.add_argument("--batch-no", required=True, help="批次编号")
        batch_parser.add_argument("--material", required=True, help="物资名称")
        batch_parser.add_argument("--quantity", type=int, required=True, help="数量")
        batch_parser.add_argument("--expiry", required=True, help="保质期 (YYYY-MM-DD)")
        batch_parser.add_argument("--location", required=True, help="存放位置")
        batch_parser.add_argument("--operator", required=True, help="操作人 (warehouse_keeper)")
        batch_parser.set_defaults(func=self._cmd_create_batch)

    def _add_request_commands(self, subparsers):
        req_parser = subparsers.add_parser(
            "create-request", help="申请人提交调拨申请", aliases=["cr"]
        )
        req_parser.add_argument("--request-no", required=True, help="申请单号")
        req_parser.add_argument("--material", required=True, help="物资名称")
        req_parser.add_argument("--quantity", type=int, required=True, help="申请数量")
        req_parser.add_argument("--location", required=True, help="安置点位置")
        req_parser.add_argument("--operator", required=True, help="操作人 (applicant)")
        req_parser.set_defaults(func=self._cmd_create_request)

        appr_parser = subparsers.add_parser(
            "approve", help="主管审批申请", aliases=["ap"]
        )
        appr_parser.add_argument("--request-id", type=int, required=True, help="申请单 ID")
        appr_parser.add_argument("--operator", required=True, help="操作人 (supervisor)")
        appr_parser.set_defaults(func=self._cmd_approve)

        reject_parser = subparsers.add_parser(
            "reject", help="主管拒绝申请", aliases=["rj"]
        )
        reject_parser.add_argument("--request-id", type=int, required=True, help="申请单 ID")
        reject_parser.add_argument("--reason", required=True, help="拒绝原因")
        reject_parser.add_argument("--operator", required=True, help="操作人 (supervisor)")
        reject_parser.set_defaults(func=self._cmd_reject)

        out_parser = subparsers.add_parser(
            "outbound", help="仓管出库", aliases=["ob"]
        )
        out_parser.add_argument("--request-id", type=int, required=True, help="申请单 ID")
        out_parser.add_argument("--operator", required=True, help="操作人 (warehouse_keeper)")
        out_parser.set_defaults(func=self._cmd_outbound)

        ret_parser = subparsers.add_parser(
            "return", help="仓管部分归还", aliases=["rt"]
        )
        ret_parser.add_argument("--request-id", type=int, required=True, help="申请单 ID")
        ret_parser.add_argument("--quantity", type=int, required=True, help="归还数量")
        ret_parser.add_argument("--operator", required=True, help="操作人 (warehouse_keeper)")
        ret_parser.set_defaults(func=self._cmd_return)

        settle_parser = subparsers.add_parser(
            "settle", help="仓管全部核销", aliases=["sl"]
        )
        settle_parser.add_argument("--request-id", type=int, required=True, help="申请单 ID")
        settle_parser.add_argument("--operator", required=True, help="操作人 (warehouse_keeper)")
        settle_parser.set_defaults(func=self._cmd_settle)

        cancel_parser = subparsers.add_parser(
            "cancel", help="申请人取消申请", aliases=["cl"]
        )
        cancel_parser.add_argument("--request-id", type=int, required=True, help="申请单 ID")
        cancel_parser.add_argument("--operator", required=True, help="操作人 (申请人本人)")
        cancel_parser.set_defaults(func=self._cmd_cancel)

        revert_parser = subparsers.add_parser(
            "revert", help="主管撤销更正(带原因)", aliases=["rv"]
        )
        revert_parser.add_argument("--request-id", type=int, required=True, help="申请单 ID")
        revert_parser.add_argument("--reason", required=True, help="撤销原因")
        revert_parser.add_argument("--operator", required=True, help="操作人 (supervisor)")
        revert_parser.set_defaults(func=self._cmd_revert)

    def _add_query_commands(self, subparsers):
        list_batches_parser = subparsers.add_parser(
            "list-batches", help="查询物资批次库存", aliases=["lb"]
        )
        list_batches_parser.add_argument("--material", help="按物资名称筛选")
        list_batches_parser.set_defaults(func=self._cmd_list_batches)

        list_requests_parser = subparsers.add_parser(
            "list-requests", help="查询调拨申请", aliases=["lr"]
        )
        list_requests_parser.add_argument("--status", help="按状态筛选")
        list_requests_parser.set_defaults(func=self._cmd_list_requests)

        logs_parser = subparsers.add_parser(
            "inventory-logs", help="查询库存变化日志", aliases=["il"]
        )
        logs_parser.add_argument("--batch-id", type=int, help="按批次 ID 筛选")
        logs_parser.add_argument("--request-id", type=int, help="按申请 ID 筛选")
        logs_parser.set_defaults(func=self._cmd_inventory_logs)

        history_parser = subparsers.add_parser(
            "operation-history", help="查询操作历史", aliases=["oh"]
        )
        history_parser.add_argument("--request-id", type=int, help="按申请 ID 筛选")
        history_parser.add_argument("--batch-id", type=int, help="按批次 ID 筛选")
        history_parser.set_defaults(func=self._cmd_operation_history)

    def _add_io_commands(self, subparsers):
        export_parser = subparsers.add_parser(
            "export", help="导出数据 (JSON/CSV)"
        )
        export_parser.add_argument("--output", required=True, help="输出文件路径")
        export_parser.add_argument(
            "--format", default="json", choices=["json", "csv"], help="导出格式"
        )
        export_parser.set_defaults(func=self._cmd_export)

        import_parser = subparsers.add_parser(
            "import", help="导入数据 (JSON/CSV)"
        )
        import_parser.add_argument("--input", required=True, help="输入文件路径")
        import_parser.add_argument(
            "--format", default="json", choices=["json", "csv"], help="导入格式"
        )
        import_parser.set_defaults(func=self._cmd_import)

    def _print_batches(self, batches: List[MaterialBatch]):
        if not batches:
            print("(无数据)")
            return
        header = f"{'ID':>4} {'批次号':<12} {'物资':<12} {'总数量':>8} {'锁定':>6} {'可用':>6} {'保质期':<12} {'过期':<6} {'位置':<12} {'录入人':<16}"
        print(header)
        print("-" * len(header))
        for b in batches:
            expired_flag = "是" if b.is_expired else "否"
            print(
                f"{b.id:>4} {b.batch_no:<12} {b.material_name:<12} "
                f"{b.quantity:>8} {b.locked_quantity:>6} {b.available_quantity:>6} "
                f"{b.expiry_date:<12} {expired_flag:<6} {b.location:<12} {b.created_by:<16}"
            )

    def _print_requests(self, requests: List[AllocationRequest]):
        if not requests:
            print("(无数据)")
            return
        header = f"{'ID':>4} {'申请单号':<12} {'物资':<12} {'数量':>6} {'位置':<12} {'申请人':<10} {'状态':<14} {'已归还':>6} {'创建时间':<20}"
        print(header)
        print("-" * len(header))
        for r in requests:
            print(
                f"{r.id:>4} {r.request_no:<12} {r.material_name:<12} "
                f"{r.quantity:>6} {r.location:<12} {r.applicant:<10} "
                f"{r.status:<14} {r.returned_quantity:>6} {r.created_at:<20}"
            )

    def _print_logs(self, logs: List[InventoryLog]):
        if not logs:
            print("(无数据)")
            return
        header = f"{'ID':>4} {'批次ID':>8} {'申请ID':>8} {'类型':<14} {'变化量':>8} {'操作人':<16} {'时间':<20} 备注"
        print(header)
        print("-" * len(header))
        for l in logs:
            print(
                f"{l.id:>4} {l.batch_id:>8} {str(l.request_id):>8} "
                f"{l.change_type:<14} {l.quantity_change:>8} {l.operator:<16} "
                f"{l.operated_at:<20} {l.remark}"
            )

    def _print_history(self, histories: List[OperationHistory]):
        if not histories:
            print("(无数据)")
            return
        header = f"{'ID':>4} {'申请ID':>8} {'批次ID':>8} {'操作':<16} {'操作人':<16} {'时间':<20} 详情"
        print(header)
        print("-" * len(header))
        for h in histories:
            print(
                f"{h.id:>4} {str(h.request_id):>8} {str(h.batch_id):>8} "
                f"{h.operation:<16} {h.operator:<16} {h.operated_at:<20} {h.detail}"
            )

    def _cmd_create_batch(self, args):
        batch = self.rules.create_batch(
            batch_no=args.batch_no,
            material_name=args.material,
            quantity=args.quantity,
            expiry_date=args.expiry,
            location=args.location,
            operator=args.operator,
        )
        print(f"[成功] 创建物资批次：")
        self._print_batches([batch])

    def _cmd_create_request(self, args):
        request = self.rules.create_request(
            request_no=args.request_no,
            material_name=args.material,
            quantity=args.quantity,
            location=args.location,
            operator=args.operator,
        )
        print(f"[成功] 创建调拨申请：")
        self._print_requests([request])

    def _cmd_approve(self, args):
        request = self.rules.approve_request(
            request_id=args.request_id, operator=args.operator
        )
        print(f"[成功] 审批通过：")
        self._print_requests([request])

    def _cmd_reject(self, args):
        request = self.rules.reject_request(
            request_id=args.request_id, operator=args.operator, reason=args.reason
        )
        print(f"[成功] 已拒绝申请：")
        self._print_requests([request])

    def _cmd_outbound(self, args):
        request = self.rules.outbound_request(
            request_id=args.request_id, operator=args.operator
        )
        print(f"[成功] 已出库：")
        self._print_requests([request])

    def _cmd_return(self, args):
        request = self.rules.partial_return(
            request_id=args.request_id, quantity=args.quantity, operator=args.operator
        )
        print(f"[成功] 已归还 {args.quantity}：")
        self._print_requests([request])

    def _cmd_settle(self, args):
        request = self.rules.full_settle(
            request_id=args.request_id, operator=args.operator
        )
        print(f"[成功] 已全部核销：")
        self._print_requests([request])

    def _cmd_cancel(self, args):
        request = self.rules.cancel_request(
            request_id=args.request_id, operator=args.operator
        )
        print(f"[成功] 已取消申请：")
        self._print_requests([request])

    def _cmd_revert(self, args):
        request = self.rules.revert_request(
            request_id=args.request_id, reason=args.reason, operator=args.operator
        )
        print(f"[成功] 已撤销更正：")
        self._print_requests([request])

    def _cmd_list_batches(self, args):
        batches = self.db.list_batches(material_name=args.material)
        print(f"=== 物资批次 (共 {len(batches)} 条) ===")
        self._print_batches(batches)

    def _cmd_list_requests(self, args):
        requests = self.db.list_requests(status=args.status)
        print(f"=== 调拨申请 (共 {len(requests)} 条) ===")
        self._print_requests(requests)

    def _cmd_inventory_logs(self, args):
        logs = self.db.list_inventory_logs(
            batch_id=args.batch_id, request_id=args.request_id
        )
        print(f"=== 库存变化日志 (共 {len(logs)} 条) ===")
        self._print_logs(logs)

    def _cmd_operation_history(self, args):
        histories = self.db.list_operation_histories(
            request_id=args.request_id, batch_id=args.batch_id
        )
        print(f"=== 操作历史 (共 {len(histories)} 条) ===")
        self._print_history(histories)

    def _cmd_export(self, args):
        output_path = self.io.export_data(args.output, format_type=args.format)
        print(f"[成功] 数据已导出到：{output_path}")
        if args.format == "csv":
            base_name = output_path.rsplit(".", 1)[0]
            print(f"CSV 格式已生成以下文件：")
            print(f"  - {base_name}_material_batches.csv")
            print(f"  - {base_name}_allocation_requests.csv")
            print(f"  - {base_name}_inventory_logs.csv")
            print(f"  - {base_name}_operation_histories.csv")

    def _cmd_import(self, args):
        counts = self.io.import_data(args.input, format_type=args.format)
        print(f"[成功] 数据导入完成：")
        print(f"  物资批次：{counts['batches']} 条")
        print(f"  调拨申请：{counts['requests']} 条")
        print(f"  库存日志：{counts['logs']} 条")
        print(f"  操作历史：{counts['histories']} 条")


def main():
    CLI().run()


if __name__ == "__main__":
    main()
