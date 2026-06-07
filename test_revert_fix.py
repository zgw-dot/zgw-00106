#!/usr/bin/env python3
"""
回归测试：撤销更正库存账修复验证

测试场景：
1. 创建 10 件批次
2. 两个 6 件申请
3. 审批第一个并确认第二个因库存不足失败
4. 出库第一个
5. 归还 2 件
6. 撤销第一个申请
7. 核对库存不能变成 12（应恢复为 10）
8. 操作历史保留撤销原因
9. 导出的 JSON/CSV 与查询库存一致
"""

import os
import sys
import json
import shutil
import subprocess

sys.path.insert(0, '.')

def run_cli(args):
    """运行 CLI 命令并返回结果"""
    cmd = ["python", "cli.py"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=".")
    return result.returncode, result.stdout, result.stderr

def cleanup():
    """清理测试数据"""
    if os.path.exists("./data"):
        shutil.rmtree("./data")
    if os.path.exists("./test_export"):
        if os.path.isdir("./test_export"):
            shutil.rmtree("./test_export")
        else:
            os.remove("./test_export")
    for f in os.listdir("."):
        if f.startswith("test_export"):
            try:
                os.remove(f)
            except:
                pass

def assert_equal(actual, expected, msg=""):
    """断言相等"""
    if actual != expected:
        print(f"❌ 断言失败: {msg}")
        print(f"   预期: {expected}")
        print(f"   实际: {actual}")
        sys.exit(1)
    print(f"✅ {msg}")

def main():
    print("=" * 70)
    print("回归测试：撤销更正库存账修复验证")
    print("=" * 70)
    print()

    cleanup()

    print("【步骤1】创建 10 件物资批次")
    rc, out, err = run_cli([
        "cb", "--batch-no", "TEST-B001",
        "--material", "测试物资",
        "--quantity", "10",
        "--expiry", "2026-12-31",
        "--location", "测试仓库",
        "--operator", "warehouse_keeper"
    ])
    assert_equal(rc, 0, "创建批次成功")
    print()

    print("【步骤2】查询初始库存（应为 10 件）")
    rc, out, err = run_cli(["lb", "--material", "测试物资"])
    assert_equal(rc, 0, "查询库存成功")
    lines = [l.strip() for l in out.split("\n") if "TEST-B001" in l]
    assert len(lines) > 0, "找到批次数据行"
    parts = lines[0].split()
    total_qty = int(parts[3])
    locked_qty = int(parts[4])
    avail_qty = int(parts[5])
    assert_equal(total_qty, 10, "初始总库存为 10 件")
    assert_equal(locked_qty, 0, "初始锁定为 0")
    assert_equal(avail_qty, 10, "初始可用为 10 件")
    print(out)
    print()

    print("【步骤3】创建第一个 6 件申请")
    rc, out, err = run_cli([
        "cr", "--request-no", "TEST-R001",
        "--material", "测试物资",
        "--quantity", "6",
        "--location", "安置点A",
        "--operator", "applicant"
    ])
    assert_equal(rc, 0, "创建申请1成功")
    print()

    print("【步骤4】创建第二个 6 件申请")
    rc, out, err = run_cli([
        "cr", "--request-no", "TEST-R002",
        "--material", "测试物资",
        "--quantity", "6",
        "--location", "安置点B",
        "--operator", "applicant"
    ])
    assert_equal(rc, 0, "创建申请2成功")
    print()

    print("【步骤5】审批第一个申请（应成功，库存锁定 6 件）")
    rc, out, err = run_cli(["approve", "--request-id", "1", "--operator", "supervisor"])
    assert_equal(rc, 0, "审批申请1成功")
    print(out)
    print()

    print("【步骤6】审批第二个申请（应失败，库存不足）")
    rc, out, err = run_cli(["approve", "--request-id", "2", "--operator", "supervisor"])
    assert_equal(rc, 4, "审批申请2失败（库存不足，退出码 4）")
    assert "库存不足" in err, "错误信息包含'库存不足'"
    print(f"   错误信息: {err.strip()}")
    print()

    print("【步骤7】查询库存（总 10，锁定 6，可用 4）")
    rc, out, err = run_cli(["lb", "--material", "测试物资"])
    assert_equal(rc, 0, "查询库存成功")
    lines = [l.strip() for l in out.split("\n") if "TEST-B001" in l]
    parts = lines[0].split()
    total_qty = int(parts[3])
    locked_qty = int(parts[4])
    avail_qty = int(parts[5])
    assert_equal(total_qty, 10, "审批后总库存为 10 件")
    assert_equal(locked_qty, 6, "审批后锁定为 6 件")
    assert_equal(avail_qty, 4, "审批后可用为 4 件")
    print(out)
    print()

    print("【步骤8】出库第一个申请")
    rc, out, err = run_cli(["outbound", "--request-id", "1", "--operator", "warehouse_keeper"])
    assert_equal(rc, 0, "出库申请1成功")
    print(out)
    print()

    print("【步骤9】查询库存（总 4，锁定 0，可用 4）")
    rc, out, err = run_cli(["lb", "--material", "测试物资"])
    assert_equal(rc, 0, "查询库存成功")
    lines = out.split("\n")
    data_line = [l for l in lines if "TEST-B001" in l][0]
    parts = data_line.split()
    total_qty = int(parts[3])
    locked_qty = int(parts[4])
    avail_qty = int(parts[5])
    assert_equal(total_qty, 4, "出库后总库存为 4 件")
    assert_equal(locked_qty, 0, "出库后锁定为 0")
    assert_equal(avail_qty, 4, "出库后可用为 4 件")
    print(out)
    print()

    print("【步骤10】部分归还 2 件")
    rc, out, err = run_cli([
        "return", "--request-id", "1",
        "--quantity", "2",
        "--operator", "warehouse_keeper"
    ])
    assert_equal(rc, 0, "归还 2 件成功")
    print(out)
    print()

    print("【步骤11】查询库存（总 6，锁定 0，可用 6）")
    rc, out, err = run_cli(["lb", "--material", "测试物资"])
    assert_equal(rc, 0, "查询库存成功")
    lines = out.split("\n")
    data_line = [l for l in lines if "TEST-B001" in l][0]
    parts = data_line.split()
    total_qty = int(parts[3])
    locked_qty = int(parts[4])
    avail_qty = int(parts[5])
    assert_equal(total_qty, 6, "归还后总库存为 6 件")
    assert_equal(locked_qty, 0, "归还后锁定为 0")
    assert_equal(avail_qty, 6, "归还后可用为 6 件")
    print(out)
    print()

    print("【步骤12】撤销更正第一个申请（带原因）")
    revert_reason = "需求变更，物资调配有误，需撤销后重新处理"
    rc, out, err = run_cli([
        "revert", "--request-id", "1",
        "--reason", revert_reason,
        "--operator", "supervisor"
    ])
    assert_equal(rc, 0, "撤销更正成功")
    print(out)
    print()

    print("【步骤13】关键点验证：撤销后库存应为 10 件，不能是 12 件！")
    rc, out, err = run_cli(["lb", "--material", "测试物资"])
    assert_equal(rc, 0, "查询库存成功")
    lines = out.split("\n")
    data_line = [l for l in lines if "TEST-B001" in l][0]
    parts = data_line.split()
    total_qty = int(parts[3])
    locked_qty = int(parts[4])
    avail_qty = int(parts[5])
    print(f"   当前库存：总 {total_qty}，锁定 {locked_qty}，可用 {avail_qty}")

    assert_equal(total_qty, 10, f"撤销后总库存应为 10 件（净出库 6-2=4 件，6+4=10），不能是 12 件！")
    assert_equal(locked_qty, 0, "撤销后锁定应为 0")
    assert_equal(avail_qty, 10, "撤销后可用应为 10 件")

    if total_qty == 12:
        print("❌ BUG 复现：库存变成了 12 件（10-6+2+6=12），撤销时错误地恢复了全部出库数量！")
        sys.exit(1)

    print(f"✅ 库存正确：10 - 6(出库) + 2(归还) + 4(撤销恢复) = 10 件")
    print(f"   （仅恢复净出库量 6-2=4 件，没有重复加回已归还的 2 件）")
    print(out)
    print()

    print("【步骤14】验证操作历史保留撤销原因")
    rc, out, err = run_cli(["operation-history", "--request-id", "1"])
    assert_equal(rc, 0, "查询操作历史成功")
    assert "revert" in out.lower(), "操作历史包含 revert 记录"
    assert revert_reason in out, f"操作历史保留撤销原因：{revert_reason}"
    print("✅ 操作历史包含撤销更正记录及原因")
    print(out)
    print()

    print("【步骤15】验证库存日志正确")
    rc, out, err = run_cli(["inventory-logs", "--request-id", "1"])
    assert_equal(rc, 0, "查询库存日志成功")
    assert "lock" in out, "包含锁定日志"
    assert "outbound" in out, "包含出库日志"
    assert "return" in out, "包含归还日志"
    assert "revert_restore" in out, "包含撤销恢复日志"
    print("✅ 库存日志完整")
    print(out)
    print()

    print("【步骤16】导出 JSON 并验证数据一致性")
    rc, out, err = run_cli(["export", "--output", "./test_export.json", "--format", "json"])
    assert_equal(rc, 0, "导出 JSON 成功")

    with open("./test_export.json", "r", encoding="utf-8") as f:
        export_data = json.load(f)

    export_batch = export_data["material_batches"][0]
    assert_equal(export_batch["quantity"], 10, "导出的批次数量为 10（与查询一致）")
    assert_equal(export_batch["locked_quantity"], 0, "导出的锁定数量为 0（与查询一致）")

    export_request = export_data["allocation_requests"][0]
    assert_equal(export_request["status"], "reverted", "导出的申请状态为 reverted")
    assert_equal(export_request["revert_reason"], revert_reason, "导出的撤销原因与实际一致")
    assert_equal(export_request["returned_quantity"], 2, "导出的已归还数量为 2")
    print("✅ JSON 导出数据与查询一致")
    print()

    print("【步骤17】导出 CSV 并验证数据一致性")
    rc, out, err = run_cli(["export", "--output", "./test_export", "--format", "csv"])
    assert_equal(rc, 0, "导出 CSV 成功")

    import csv
    with open("./test_export_material_batches.csv", "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        csv_batch = rows[0]
        assert_equal(int(csv_batch["quantity"]), 10, "CSV 导出的批次数量为 10")
        assert_equal(int(csv_batch["locked_quantity"]), 0, "CSV 导出的锁定数量为 0")

    with open("./test_export_allocation_requests.csv", "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        csv_request = rows[0]
        assert_equal(csv_request["status"], "reverted", "CSV 导出的申请状态为 reverted")
        assert_equal(csv_request["revert_reason"], revert_reason, "CSV 导出的撤销原因一致")
        assert_equal(int(csv_request["returned_quantity"]), 2, "CSV 导出的已归还数量为 2")

    print("✅ CSV 导出数据与查询一致")
    print()

    print("【步骤18】验证撤销后第二个申请现在可以审批（库存恢复了 4 件，加上已有的 6 件共 10 件）")
    rc, out, err = run_cli(["approve", "--request-id", "2", "--operator", "supervisor"])
    assert_equal(rc, 0, "撤销后申请2可以审批成功（库存恢复为 10 件）")
    print("✅ 库存恢复正确，第二个申请可以正常审批")
    print(out)
    print()

    print("=" * 70)
    print("🎉 所有回归测试通过！")
    print("=" * 70)
    print()
    print("修复总结：")
    print("  1. 撤销更正时计算净出库量 = 申请总数量 - 已归还数量")
    print("  2. 只恢复净出库量，避免重复加回已归还部分")
    print("  3. 仅 APPROVED 状态才解锁锁定库存（出库后 locked_quantity 已减少）")
    print("  4. 导出的 JSON/CSV 与实际查询数据保持一致")

    cleanup()

if __name__ == "__main__":
    main()
