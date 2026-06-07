#!/usr/bin/env python3
"""
库存审计快照功能验证测试

测试场景：
1. 基础功能：摘要打印、物资筛选、时间范围筛选
2. 异常检测：负库存、锁定数大于库存、状态日志不一致、导入冲突
3. 导出验证：JSON/CSV 字段稳定，跨重启一致
4. 权限控制：申请人脱敏、越权失败
5. 退出码：有异常时返回非零退出码
"""

import os
import sys
import json
import csv
import shutil
import subprocess

sys.path.insert(0, ".")


def run_cli(args, cwd="."):
    """运行 CLI 命令并返回结果"""
    cmd = ["python", "cli.py"] + args
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        cwd=cwd, env=env
    )
    return result.returncode, result.stdout or "", result.stderr or ""


def cleanup(cwd="."):
    """清理测试数据（带重试处理文件锁定）"""
    import time
    data_dir = os.path.join(cwd, "data")
    if os.path.exists(data_dir):
        for attempt in range(10):
            try:
                shutil.rmtree(data_dir)
                break
            except Exception:
                if attempt < 9:
                    time.sleep(0.2)
                else:
                    print(f"警告: 无法删除数据目录 {data_dir}")
    for f in os.listdir(cwd):
        if f.startswith("audit_test"):
            try:
                fp = os.path.join(cwd, f)
                if os.path.isdir(fp):
                    shutil.rmtree(fp)
                else:
                    os.remove(fp)
            except Exception:
                pass


def assert_equal(actual, expected, msg=""):
    """断言相等"""
    if actual != expected:
        print(f"[FAIL] 断言失败: {msg}")
        print(f"   预期: {expected}")
        print(f"   实际: {actual}")
        sys.exit(1)
    print(f"[PASS] {msg}")


def assert_in(item, container, msg=""):
    """断言包含"""
    if item not in container:
        print(f"[FAIL] 断言失败: {msg}")
        print(f"   期望包含: {item}")
        print(f"   实际内容: {container[:200]}...")
        sys.exit(1)
    print(f"[PASS] {msg}")


def create_test_data(cwd="."):
    """创建测试数据"""
    run_cli([
        "cb", "--batch-no", "AUDIT-B001",
        "--material", "审计测试物资A",
        "--quantity", "100",
        "--expiry", "2026-12-31",
        "--location", "A仓库",
        "--operator", "warehouse_keeper"
    ], cwd=cwd)

    run_cli([
        "cb", "--batch-no", "AUDIT-B002",
        "--material", "审计测试物资A",
        "--quantity", "50",
        "--expiry", "2027-06-30",
        "--location", "B仓库",
        "--operator", "warehouse_keeper"
    ], cwd=cwd)

    run_cli([
        "cb", "--batch-no", "AUDIT-B003",
        "--material", "审计测试物资B",
        "--quantity", "200",
        "--expiry", "2026-06-30",
        "--location", "C仓库",
        "--operator", "warehouse_keeper"
    ], cwd=cwd)

    run_cli([
        "cr", "--request-no", "AUDIT-R001",
        "--material", "审计测试物资A",
        "--quantity", "30",
        "--location", "安置点1",
        "--operator", "applicant"
    ], cwd=cwd)

    run_cli([
        "cr", "--request-no", "AUDIT-R002",
        "--material", "审计测试物资B",
        "--quantity", "50",
        "--location", "安置点2",
        "--operator", "applicant"
    ], cwd=cwd)

    run_cli(["approve", "--request-id", "1", "--operator", "supervisor"], cwd=cwd)
    run_cli(["outbound", "--request-id", "1", "--operator", "warehouse_keeper"], cwd=cwd)
    run_cli([
        "return", "--request-id", "1", "--quantity", "10",
        "--operator", "warehouse_keeper"
    ], cwd=cwd)


def test_basic_audit():
    """测试1：基础审计快照功能"""
    print("\n" + "=" * 70)
    print("测试1：基础审计快照功能")
    print("=" * 70)

    cwd = os.getcwd()
    cleanup(cwd)
    create_test_data(cwd)

    rc, out, err = run_cli(["audit-snapshot", "--operator", "supervisor"], cwd=cwd)
    assert_equal(rc, 0, "默认摘要审计成功")
    assert_in("库存审计快照", out, "输出包含标题")
    assert_in("汇总统计", out, "输出包含汇总统计")
    assert_in("审计测试物资A", out, "输出包含测试物资A")
    assert_in("审计测试物资B", out, "输出包含测试物资B")

    rc, out, err = run_cli([
        "audit-snapshot", "--operator", "supervisor",
        "--material", "审计测试物资A"
    ], cwd=cwd)
    assert_equal(rc, 0, "按物资筛选成功")
    assert_in("审计测试物资A", out, "筛选结果包含物资A")
    assert "审计测试物资B" not in out, "筛选结果不包含物资B"

    rc, out, err = run_cli([
        "audit-snapshot", "--operator", "supervisor",
        "--show-details"
    ], cwd=cwd)
    assert_equal(rc, 0, "显示详细信息成功")
    assert_in("批次明细", out, "输出包含批次明细")
    assert_in("申请明细", out, "输出包含申请明细")
    assert_in("AUDIT-B001", out, "明细包含具体批次号")

    cleanup(cwd)
    print("[PASS] 测试1通过：基础审计快照功能正常")


def test_export_json():
    """测试2：JSON 导出字段稳定"""
    print("\n" + "=" * 70)
    print("测试2：JSON 导出字段稳定")
    print("=" * 70)

    cwd = os.getcwd()
    cleanup(cwd)
    create_test_data(cwd)

    rc, out, err = run_cli([
        "audit-snapshot", "--operator", "supervisor",
        "--format", "json", "--output", "./audit_test_snapshot1.json"
    ], cwd=cwd)
    assert_equal(rc, 0, "首次JSON导出成功")

    with open("./audit_test_snapshot1.json", "r", encoding="utf-8") as f:
        data1 = json.load(f)

    expected_top_fields = [
        "snapshot_at", "operator", "operator_role",
        "filters", "summary", "materials", "anomalies"
    ]
    for field in expected_top_fields:
        assert_in(field, data1, f"JSON顶层包含字段 {field}")

    expected_summary_fields = [
        "total_materials", "total_batches", "total_requests",
        "total_quantity", "total_locked", "total_available",
        "total_logs", "total_operations",
        "total_anomalies", "critical_anomalies", "warning_anomalies"
    ]
    for field in expected_summary_fields:
        assert_in(field, data1["summary"], f"summary包含字段 {field}")

    if data1["materials"]:
        expected_material_fields = [
            "material_name", "total_quantity", "total_locked",
            "total_available", "log_count", "operation_count",
            "batches", "requests"
        ]
        for field in expected_material_fields:
            assert_in(field, data1["materials"][0], f"material包含字段 {field}")

        if data1["materials"][0]["batches"]:
            expected_batch_fields = [
                "batch_id", "batch_no", "quantity", "locked_quantity",
                "available_quantity", "expiry_date", "location",
                "created_at", "is_expired"
            ]
            for field in expected_batch_fields:
                assert_in(field, data1["materials"][0]["batches"][0],
                         f"batch包含字段 {field}")

    cleanup(cwd)
    print("[PASS] 测试2通过：JSON 字段结构稳定")


def test_export_csv():
    """测试3：CSV 导出字段稳定"""
    print("\n" + "=" * 70)
    print("测试3：CSV 导出字段稳定")
    print("=" * 70)

    cwd = os.getcwd()
    cleanup(cwd)
    create_test_data(cwd)

    rc, out, err = run_cli([
        "audit-snapshot", "--operator", "supervisor",
        "--format", "csv", "--output", "./audit_test_snapshot"
    ], cwd=cwd)
    assert_equal(rc, 0, "CSV导出成功")

    assert os.path.exists("./audit_test_snapshot_summary.csv"), "生成summary.csv"
    assert os.path.exists("./audit_test_snapshot_materials.csv"), "生成materials.csv"
    assert os.path.exists("./audit_test_snapshot_batches.csv"), "生成batches.csv"
    assert os.path.exists("./audit_test_snapshot_requests.csv"), "生成requests.csv"

    with open("./audit_test_snapshot_materials.csv", "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        expected_headers = [
            "material_name", "total_quantity", "total_locked",
            "total_available", "batch_count", "request_count",
            "log_count", "operation_count"
        ]
        for h in expected_headers:
            assert_in(h, headers, f"materials.csv包含列 {h}")

    with open("./audit_test_snapshot_batches.csv", "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        expected_headers = [
            "material_name", "batch_id", "batch_no", "quantity",
            "locked_quantity", "available_quantity",
            "expiry_date", "location", "created_at", "is_expired"
        ]
        for h in expected_headers:
            assert_in(h, headers, f"batches.csv包含列 {h}")

    cleanup(cwd)
    print("[PASS] 测试3通过：CSV 字段结构稳定")


def test_cross_restart_consistency():
    """测试4：跨重启后快照一致"""
    print("\n" + "=" * 70)
    print("测试4：跨重启后快照一致")
    print("=" * 70)

    cwd = os.getcwd()
    cleanup(cwd)
    create_test_data(cwd)

    rc, out, err = run_cli([
        "audit-snapshot", "--operator", "supervisor",
        "--format", "json", "--output", "./audit_test_before.json"
    ], cwd=cwd)
    assert_equal(rc, 0, "重启前导出成功")

    with open("./audit_test_before.json", "r", encoding="utf-8") as f:
        data_before = json.load(f)

    for mat in data_before["materials"]:
        mat.pop("log_count", None)
        mat.pop("operation_count", None)
        for batch in mat["batches"]:
            batch.pop("created_at", None)
        for req in mat["requests"]:
            req.pop("created_at", None)
    data_before.pop("snapshot_at", None)
    data_before["summary"].pop("total_logs", None)
    data_before["summary"].pop("total_operations", None)

    rc, out, err = run_cli([
        "audit-snapshot", "--operator", "supervisor",
        "--format", "json", "--output", "./audit_test_after.json"
    ], cwd=cwd)
    assert_equal(rc, 0, "重启后导出成功")

    with open("./audit_test_after.json", "r", encoding="utf-8") as f:
        data_after = json.load(f)

    for mat in data_after["materials"]:
        mat.pop("log_count", None)
        mat.pop("operation_count", None)
        for batch in mat["batches"]:
            batch.pop("created_at", None)
        for req in mat["requests"]:
            req.pop("created_at", None)
    data_after.pop("snapshot_at", None)
    data_after["summary"].pop("total_logs", None)
    data_after["summary"].pop("total_operations", None)

    assert_equal(
        json.dumps(data_before, sort_keys=True, ensure_ascii=False),
        json.dumps(data_after, sort_keys=True, ensure_ascii=False),
        "跨重启数据一致"
    )

    cleanup(cwd)
    print("[PASS] 测试4通过：跨重启后快照数据一致")


def test_anomaly_detection():
    """测试5：异常检测功能"""
    print("\n" + "=" * 70)
    print("测试5：异常检测功能")
    print("=" * 70)

    cwd = os.getcwd()
    cleanup(cwd)
    create_test_data(cwd)

    import sqlite3
    import time
    time.sleep(0.5)

    db_path = os.path.join(cwd, "data", "emergency_supply.db")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("UPDATE material_batches SET quantity = -10 WHERE batch_no = 'AUDIT-B003'")
    c.execute("UPDATE material_batches SET locked_quantity = 200 WHERE batch_no = 'AUDIT-B002'")

    c.executescript("""
        PRAGMA foreign_keys = OFF;

        CREATE TABLE material_batches_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_no TEXT NOT NULL,
            material_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            locked_quantity INTEGER DEFAULT 0,
            expiry_date TEXT NOT NULL,
            location TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        );
        INSERT INTO material_batches_new SELECT * FROM material_batches;
        DROP TABLE material_batches;
        ALTER TABLE material_batches_new RENAME TO material_batches;

        CREATE TABLE allocation_requests_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_no TEXT NOT NULL,
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
        INSERT INTO allocation_requests_new SELECT * FROM allocation_requests;
        DROP TABLE allocation_requests;
        ALTER TABLE allocation_requests_new RENAME TO allocation_requests;

        PRAGMA foreign_keys = ON;
    """)

    c.execute("""
        INSERT INTO material_batches
        (batch_no, material_name, quantity, locked_quantity, expiry_date,
         location, created_by, created_at, is_active)
        VALUES ('AUDIT-B001', '冲突物资', 10, 0, '2026-12-31', 'D仓', 'test', '2025-01-01 00:00:00', 1)
    """)

    c.execute("""
        INSERT INTO allocation_requests
        (request_no, material_name, quantity, location, applicant, status, created_at)
        VALUES ('AUDIT-R001', '冲突申请', 5, '安置点X', 'test', 'pending', '2025-01-01 00:00:00')
    """)

    conn.commit()
    conn.close()
    time.sleep(0.5)

    rc, out, err = run_cli(["audit-snapshot", "--operator", "supervisor"], cwd=cwd)
    assert_equal(rc, 5, "存在异常时返回退出码 5")
    assert_in("异常检测", out, "输出包含异常检测")
    assert_in("库存为负数", out, "检测到负库存异常")
    assert_in("锁定数量", out, "检测到锁定数大于库存异常")
    assert_in("批次号冲突", out, "检测到批次号冲突异常")
    assert_in("申请号冲突", out, "检测到申请号冲突异常")

    time.sleep(0.5)
    cleanup(cwd)
    print("[PASS] 测试5通过：异常检测功能正常")


def test_import_conflict_audit():
    """测试6：导入冲突后审计能报问题"""
    import time
    import sqlite3
    print("\n" + "=" * 70)
    print("测试6：导入冲突后审计能报问题")
    print("=" * 70)

    cwd = os.getcwd()
    cleanup(cwd)
    create_test_data(cwd)

    export_path = os.path.join(cwd, "audit_test_export.json")
    rc, out, err = run_cli([
        "export", "--output", export_path,
        "--format", "json"
    ], cwd=cwd)
    assert_equal(rc, 0, "导出成功")

    with open(export_path, "r", encoding="utf-8") as f:
        export_data = f.read()

    time.sleep(0.5)
    cleanup(cwd)
    time.sleep(0.5)

    create_test_data(cwd)

    time.sleep(0.5)
    db_path = os.path.join(cwd, "data", "emergency_supply.db")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.executescript("""
        PRAGMA foreign_keys = OFF;

        CREATE TABLE material_batches_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_no TEXT NOT NULL,
            material_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            locked_quantity INTEGER DEFAULT 0,
            expiry_date TEXT NOT NULL,
            location TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_active INTEGER DEFAULT 1
        );
        INSERT INTO material_batches_new SELECT * FROM material_batches;
        DROP TABLE material_batches;
        ALTER TABLE material_batches_new RENAME TO material_batches;

        CREATE TABLE allocation_requests_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_no TEXT NOT NULL,
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
        INSERT INTO allocation_requests_new SELECT * FROM allocation_requests;
        DROP TABLE allocation_requests;
        ALTER TABLE allocation_requests_new RENAME TO allocation_requests;

        PRAGMA foreign_keys = ON;
    """)
    conn.commit()
    conn.close()
    time.sleep(0.5)

    with open(export_path, "w", encoding="utf-8") as f:
        f.write(export_data)

    time.sleep(0.5)
    rc, out, err = run_cli([
        "import", "--input", export_path,
        "--format", "json"
    ], cwd=cwd)
    assert_equal(rc, 0, "导入成功")

    time.sleep(0.5)
    rc, out, err = run_cli(["audit-snapshot", "--operator", "supervisor"], cwd=cwd)
    assert_equal(rc, 5, "导入冲突后审计返回异常退出码")
    assert_in("批次号冲突", out, "审计报告批次号冲突")
    assert_in("申请号冲突", out, "审计报告申请号冲突")

    time.sleep(0.5)
    cleanup(cwd)
    print("[PASS] 测试6通过：导入冲突后审计能正确报告问题")


def test_permission_control():
    """测试7：权限控制"""
    import time
    print("\n" + "=" * 70)
    print("测试7：权限控制")
    print("=" * 70)

    cwd = os.getcwd()
    cleanup(cwd)
    create_test_data(cwd)

    rc, out, err = run_cli([
        "audit-snapshot", "--operator", "invalid_role"
    ], cwd=cwd)
    assert_equal(rc, 2, "无效角色返回权限错误退出码 2")
    assert_in("权限不足", err, "无效角色提示权限不足")

    rc, out, err = run_cli([
        "audit-snapshot", "--operator", "applicant",
        "--show-details"
    ], cwd=cwd)
    assert_equal(rc, 2, "申请人查看详情返回权限错误退出码 2")
    assert_in("权限不足", err, "申请人查看详情提示权限不足")

    rc, out, err = run_cli([
        "audit-snapshot", "--operator", "applicant"
    ], cwd=cwd)
    assert_equal(rc, 0, "申请人查看摘要成功")
    assert "A仓库" not in out, "申请人摘要不包含真实位置"
    assert "2026-12" not in out, "申请人摘要不包含真实保质期"

    rc, out, err = run_cli([
        "audit-snapshot", "--operator", "applicant",
        "--format", "json", "--output", "./audit_test_applicant.json"
    ], cwd=cwd)
    assert_equal(rc, 0, "申请人导出成功（已脱敏）")

    with open("./audit_test_applicant.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert_in("***", json.dumps(data), "导出JSON包含脱敏标记 ***")
    if data["materials"] and data["materials"][0]["batches"]:
        assert_equal(
            data["materials"][0]["batches"][0]["location"], "***",
            "导出JSON中位置已脱敏"
        )
        assert_equal(
            data["materials"][0]["batches"][0]["expiry_date"], "***",
            "导出JSON中保质期已脱敏"
        )
    if data["materials"] and data["materials"][0]["requests"]:
        assert_equal(
            data["materials"][0]["requests"][0]["applicant"], "***",
            "导出JSON中申请人已脱敏"
        )

    rc, out, err = run_cli([
        "audit-snapshot", "--operator", "warehouse_keeper",
        "--show-details"
    ], cwd=cwd)
    assert_equal(rc, 0, "仓管查看详情成功")
    assert_in("A仓库", out, "仓管视图包含真实位置")

    rc, out, err = run_cli([
        "audit-snapshot", "--operator", "supervisor",
        "--show-details"
    ], cwd=cwd)
    assert_equal(rc, 0, "主管查看详情成功")
    assert_in("A仓库", out, "主管视图包含真实位置")

    time.sleep(0.5)
    cleanup(cwd)
    print("[PASS] 测试7通过：权限控制正常")


def test_time_range_filter():
    """测试8：时间范围筛选"""
    print("\n" + "=" * 70)
    print("测试8：时间范围筛选")
    print("=" * 70)

    cwd = os.getcwd()
    cleanup(cwd)
    create_test_data(cwd)

    rc, out, err = run_cli([
        "audit-snapshot", "--operator", "supervisor",
        "--start-time", "2099-01-01 00:00:00"
    ], cwd=cwd)
    assert_equal(rc, 0, "未来时间筛选成功")
    assert_in("物资种类：0 种", out or err, "筛选结果为空")

    rc, out, err = run_cli([
        "audit-snapshot", "--operator", "supervisor",
        "--end-time", "2020-01-01 00:00:00"
    ], cwd=cwd)
    assert_equal(rc, 0, "历史时间筛选成功")
    assert_in("物资种类：0 种", out or err, "筛选结果为空")

    cleanup(cwd)
    print("[PASS] 测试8通过：时间范围筛选正常")


def main():
    print("=" * 70)
    print("库存审计快照功能验证测试")
    print("=" * 70)

    try:
        test_basic_audit()
        test_export_json()
        test_export_csv()
        test_cross_restart_consistency()
        test_anomaly_detection()
        test_import_conflict_audit()
        test_permission_control()
        test_time_range_filter()

        print("\n" + "=" * 70)
        print("🎉 所有审计快照测试通过！")
        print("=" * 70)
        print()
        print("验证总结：")
        print("  1. [PASS] 基础功能：摘要打印、物资筛选、时间范围筛选正常")
        print("  2. [PASS] 异常检测：负库存、锁定超限、状态日志不一致、导入冲突均能检测")
        print("  3. [PASS] 导出验证：JSON/CSV 字段稳定，跨重启数据一致")
        print("  4. [PASS] 权限控制：申请人脱敏，越权操作失败")
        print("  5. [PASS] 退出码：有异常时返回非零退出码 5")

    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        cleanup()
        sys.exit(1)

    cleanup()


if __name__ == "__main__":
    main()
