# 社区应急物资调拨管理系统 (CLI)

基于 Python + SQLite 的本地社区应急物资调拨 CLI 管理工具，支持多角色权限控制、完整状态流转、库存锁定、操作追溯、数据导入导出等功能。

## 功能特性

### 核心业务流程
- **物资录入**：仓管录入物资批次（批次号、物资名称、数量、保质期、存放位置）
- **申请调拨**：申请人提交安置点物资调拨需求
- **审批锁定**：主管审批后自动锁定对应库存（先过期先出）
- **出库发放**：仓管根据审批结果完成出库
- **归还核销**：支持部分归还、全部核销
- **取消撤销**：申请人可取消待处理申请，主管可带原因撤销更正

### 权限控制
| 角色 | 仓管 (warehouse_keeper) | 申请人 (applicant) | 主管 (supervisor) |
|------|------------------------|-------------------|------------------|
| 录入物资批次 | ✅ | ❌ | ❌ |
| 提交调拨申请 | ❌ | ✅ | ❌ |
| 审批申请 | ❌ | ❌ | ✅ |
| 拒绝申请 | ❌ | ❌ | ✅ |
| 出库发放 | ✅ | ❌ | ❌ |
| 部分归还 | ✅ | ❌ | ❌ |
| 全部核销 | ✅ | ❌ | ❌ |
| 取消申请 | ❌ | ✅(本人) | ❌ |
| 撤销更正 | ❌ | ❌ | ✅ |
| 查询库存/日志 | ✅ | ✅ | ✅ |
| 导入导出 | ✅ | ✅ | ✅ |
| 库存审计快照(完整) | ✅ | ❌ | ✅ |
| 库存审计快照(脱敏) | ❌ | ✅ | ❌ |

### 状态流转
```
pending(待审批) → approved(已审批) → outbound(已出库) → partial_return(部分归还)
                                                         ↘ full_settled(全部核销)
                  ↘ rejected(已拒绝)
                  ↘ cancelled(已取消) [申请人]
已处理状态 → reverted(已撤销) [主管，带原因]
```

### 错误防护
- **库存不足**：审批时检测有效库存，不足则拒绝审批
- **批次过期**：过期批次不参与分配，审批时明确提示
- **权限越权**：申请人无法执行审批、出库、撤销等操作
- **状态非法**：终态申请不可再操作，跳过审批不能直接出库
- **重复归还**：已全部归还的申请禁止重复归还
- **超量归还**：归还数量不得超过未归还数量

### 数据持久化
- 所有数据存储于本地 SQLite 数据库，重启 CLI 不丢失
- 完整记录每笔库存变化和操作历史，可追溯
- 支持 JSON/CSV 格式导入导出，数据一致性保证

## 快速开始

### 环境要求
- Python >= 3.8
- 无需额外依赖（使用 Python 标准库）

### 使用方式
```bash
# 查看帮助
python cli.py --help

# 查看命令帮助
python cli.py create-batch --help
```

## 命令速览

### 物资管理
| 命令 | 别名 | 说明 |
|------|------|------|
| `create-batch` | `cb` | 仓管录入物资批次 |
| `list-batches` | `lb` | 查询物资批次库存 |

### 申请管理
| 命令 | 别名 | 说明 |
|------|------|------|
| `create-request` | `cr` | 申请人提交调拨申请 |
| `approve` | `ap` | 主管审批申请 |
| `reject` | `rj` | 主管拒绝申请 |
| `outbound` | `ob` | 仓管出库 |
| `return` | `rt` | 仓管部分归还 |
| `settle` | `sl` | 仓管全部核销 |
| `cancel` | `cl` | 申请人取消申请 |
| `revert` | `rv` | 主管撤销更正（带原因） |
| `list-requests` | `lr` | 查询调拨申请 |

### 查询功能
| 命令 | 别名 | 说明 |
|------|------|------|
| `inventory-logs` | `il` | 查询库存变化日志 |
| `operation-history` | `oh` | 查询操作历史 |
| `audit-snapshot` | `as` | 库存审计快照（演练/灾后复盘） |

### 数据导入导出
| 命令 | 说明 |
|------|------|
| `export` | 导出数据（JSON/CSV） |
| `import` | 导入数据（JSON/CSV） |

## 使用示例

### 1. 仓管录入物资批次
```bash
# 录入 100 件矿泉水，保质期到 2026-12-31，存放在 A 仓库
python cli.py create-batch --batch-no B2025001 --material 矿泉水 --quantity 100 \
  --expiry 2026-12-31 --location A仓库 --operator warehouse_keeper
```

### 2. 申请人提交调拨需求
```bash
# 申请 30 件矿泉水送往安置点1
python cli.py create-request --request-no R2025001 --material 矿泉水 --quantity 30 \
  --location 安置点1 --operator applicant
```

### 3. 主管审批
```bash
# 审批 ID 为 1 的申请（审批通过后库存自动锁定）
python cli.py approve --request-id 1 --operator supervisor
```

### 4. 仓管出库
```bash
# 对 ID 为 1 的申请执行出库
python cli.py outbound --request-id 1 --operator warehouse_keeper
```

### 5. 部分归还
```bash
# 归还 10 件（剩余 20 件已使用待核销）
python cli.py return --request-id 1 --quantity 10 --operator warehouse_keeper
```

### 6. 全部核销
```bash
# 核销剩余未归还部分，流程结束
python cli.py settle --request-id 1 --operator warehouse_keeper
```

### 7. 查询库存
```bash
# 查看所有物资批次
python cli.py list-batches

# 查看矿泉水库存
python cli.py list-batches --material 矿泉水
```

### 8. 查询申请
```bash
# 查看所有申请
python cli.py list-requests

# 查看待审批的申请
python cli.py list-requests --status pending
```

### 9. 查询操作历史
```bash
# 查看申请单 1 的所有操作历史
python cli.py operation-history --request-id 1

# 查看批次 1 的库存变化日志
python cli.py inventory-logs --batch-id 1
```

### 10. 导入导出
```bash
# 导出为 JSON
python cli.py export --output ./data/export.json --format json

# 导出为 CSV（生成4个CSV文件）
python cli.py export --output ./data/export --format csv

# 导入 JSON 数据
python cli.py import --input ./data/export.json --format json
```

### 11. 库存审计快照（演练/灾后复盘）
```bash
# 主管查看完整审计快照（默认摘要）
python cli.py audit-snapshot --operator supervisor

# 按物资名称筛选审计
python cli.py audit-snapshot --operator supervisor --material 矿泉水

# 按时间范围筛选审计
python cli.py audit-snapshot --operator supervisor --start-time "2025-01-01 00:00:00" --end-time "2025-12-31 23:59:59"

# 显示详细信息（批次、申请明细）
python cli.py audit-snapshot --operator supervisor --show-details

# 导出为 JSON（完整数据，仓管/主管可用）
python cli.py audit-snapshot --operator supervisor --format json --output ./audit/snapshot.json

# 导出为 CSV（生成多个CSV文件）
python cli.py audit-snapshot --operator warehouse_keeper --format csv --output ./audit/snapshot

# 申请人查看脱敏摘要
python cli.py audit-snapshot --operator applicant

# 申请人导出脱敏数据
python cli.py audit-snapshot --operator applicant --format json --output ./audit/applicant_snapshot.json

# 使用别名
python cli.py as --operator supervisor --show-details
```

### 12. 审计异常说明
审计快照会自动检测以下异常，发现异常时退出码为 5：

| 异常类型 | 说明 |
|---------|------|
| 负库存 | 批次库存数量为负数 |
| 锁定数大于库存 | 批次锁定数量超过实际库存 |
| 申请状态与日志不一致 | 申请状态与对应库存日志数量不匹配 |
| 批次号冲突 | 数据库中存在重复的批次号 |
| 申请号冲突 | 数据库中存在重复的申请号 |

## 非法场景测试

### 库存不足场景
```bash
# 录入 10 件物资
python cli.py cb --batch-no B001 --material 帐篷 --quantity 10 --expiry 2026-12-31 \
  --location A仓 --operator warehouse_keeper

# 申请 20 件（超过库存）
python cli.py cr --request-no R001 --material 帐篷 --quantity 20 --location 安置点1 \
  --operator applicant

# 审批失败 - 库存不足
python cli.py approve --request-id 1 --operator supervisor
# [库存错误] 库存不足：申请 '帐篷' x20，有效库存仅 10。
```

### 批次过期场景
```bash
# 录入已过期物资
python cli.py cb --batch-no B002 --material 急救包 --quantity 50 --expiry 2020-01-01 \
  --location B仓 --operator warehouse_keeper

# 申请 10 件
python cli.py cr --request-no R002 --material 急救包 --quantity 10 --location 安置点2 \
  --operator applicant

# 审批失败 - 批次过期
python cli.py approve --request-id 2 --operator supervisor
# [库存错误] 库存不足且存在过期批次：申请 '急救包' x10，有效库存仅 0，另有 50 已过期不可用。
```

### 权限越权场景
```bash
# 申请人尝试审批
python cli.py approve --request-id 1 --operator applicant
# [权限错误] 权限不足：用户 'applicant' 没有权限执行此操作。允许的角色：supervisor

# 申请人尝试出库
python cli.py outbound --request-id 1 --operator applicant
# [权限错误] 权限不足：用户 'applicant' 没有权限执行此操作。允许的角色：warehouse_keeper
```

### 跳过审批出库
```bash
# 申请未审批直接出库
python cli.py outbound --request-id 1 --operator warehouse_keeper
# [状态错误] 无法出库：申请单 'R001' 尚未审批，请先由主管审批后再出库。
```

### 重复/超量归还
```bash
# 申请 10 件，已全部出库
# 尝试归还 15 件（超过申请数量）
python cli.py return --request-id 1 --quantity 15 --operator warehouse_keeper
# [库存错误] 超量归还：申请单 'R001' 未归还数量为 10，申请归还 15，超出部分不允许。

# 全部归还后再次归还
python cli.py return --request-id 1 --quantity 10 --operator warehouse_keeper  # 第一次
python cli.py return --request-id 1 --quantity 5 --operator warehouse_keeper   # 第二次
# [状态错误] 无法归还：申请单 'R001' 已全部归还（10/10），请使用全部核销或检查是否重复归还。
```

### 终态不可操作
```bash
# 已拒绝的申请无法审批
python cli.py approve --request-id 2 --operator supervisor
# [状态错误] 无法执行 '审批'：申请单 'R002' 当前状态为 'rejected'，已处于终态，不可再操作。
```

### 撤销更正需带原因
```bash
python cli.py revert --request-id 1 --reason "" --operator supervisor
# [业务错误] 撤销更正必须提供原因说明。

python cli.py revert --request-id 1 --reason "数据录入错误，需重新处理" --operator supervisor
# [成功] 已撤销更正
```

## 回归验证：撤销更正库存账

### 问题场景
申请出库后如果先部分归还，再执行撤销更正，原实现会把已经归还过的数量又恢复一次，导致批次库存超过初始数量。

**复现步骤：**
```bash
# 1. 创建 10 件批次
python cli.py cb --batch-no B001 --material 测试物资 --quantity 10 --expiry 2026-12-31 --location 仓库 --operator warehouse_keeper

# 2. 创建两个 6 件申请
python cli.py cr --request-no R001 --material 测试物资 --quantity 6 --location 安置点A --operator applicant
python cli.py cr --request-no R002 --material 测试物资 --quantity 6 --location 安置点B --operator applicant

# 3. 审批第一个（成功），第二个因库存不足失败
python cli.py approve --request-id 1 --operator supervisor  # 成功，锁定 6 件
python cli.py approve --request-id 2 --operator supervisor  # [库存错误] 库存不足

# 4. 出库第一个申请
python cli.py outbound --request-id 1 --operator warehouse_keeper  # 库存变为 4 件

# 5. 部分归还 2 件
python cli.py return --request-id 1 --quantity 2 --operator warehouse_keeper  # 库存变为 6 件

# 6. 撤销更正（带原因）
python cli.py revert --request-id 1 --reason "需求变更，需重新处理" --operator supervisor
```

**结果验证：**
```bash
# 查询库存 - 正确应为 10 件，不能是 12 件
python cli.py lb --material 测试物资
#   ID 批次号    物资      总数量  锁定  可用 ...
#    1 B001    测试物资     10     0    10 ...

# 验证逻辑：10 - 6(出库) + 2(归还) + 4(撤销恢复净出库) = 10 ✓
# 错误逻辑：10 - 6(出库) + 2(归还) + 6(撤销恢复全部出库) = 12 ✗

# 操作历史保留撤销原因
python cli.py operation-history --request-id 1
# ... revert  supervisor ... 撤销更正：原因：需求变更，需重新处理...

# 第二个申请现在可以审批了（库存恢复为 10 件）
python cli.py approve --request-id 2 --operator supervisor  # 成功
```

**导出一致性验证：**
```bash
# 导出 JSON
python cli.py export --output ./test_export.json --format json

# 验证导出数据与查询一致
python -c "
import json
with open('test_export.json') as f:
    data = json.load(f)
batch = [b for b in data['material_batches'] if b['batch_no'] == 'B001'][0]
req = [r for r in data['allocation_requests'] if r['request_no'] == 'R001'][0]
assert batch['quantity'] == 10, '批次数量应为 10'
assert batch['locked_quantity'] == 0, '锁定数量应为 0'
assert req['status'] == 'reverted', '状态应为 reverted'
assert req['returned_quantity'] == 2, '已归还数量应为 2'
print('导出数据与查询一致 ✓')
"
```

运行完整回归测试：
```bash
python test_revert_fix.py
```

## 项目结构

```
.
├── cli.py                      # CLI 入口脚本
├── requirements.txt            # 依赖说明（无额外依赖）
├── README.md                   # 本文件
├── data/
│   └── emergency_supply.db     # SQLite 数据库（自动创建）
└── emergency_supply_cli/       # 主包
    ├── __init__.py
    ├── config.py               # 配置（角色、状态、路径）
    ├── models.py               # 数据模型（dataclass）
    ├── database.py             # SQLite 存储层
    ├── rules.py                # 业务规则与状态机
    ├── io.py                   # 导入导出功能
    └── main.py                 # CLI 命令解析与执行
```

## 数据模型

### material_batches (物资批次表)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| batch_no | TEXT | 批次编号（唯一） |
| material_name | TEXT | 物资名称 |
| quantity | INTEGER | 总数量 |
| locked_quantity | INTEGER | 已锁定数量 |
| expiry_date | TEXT | 保质期 (YYYY-MM-DD) |
| location | TEXT | 存放位置 |
| created_by | TEXT | 录入人 |
| created_at | TEXT | 创建时间 |
| is_active | INTEGER | 是否启用 |

### allocation_requests (调拨申请表)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| request_no | TEXT | 申请单号（唯一） |
| material_name | TEXT | 物资名称 |
| quantity | INTEGER | 申请数量 |
| location | TEXT | 安置点位置 |
| applicant | TEXT | 申请人 |
| status | TEXT | 状态 |
| created_at | TEXT | 创建时间 |
| approved_at/by | TEXT | 审批时间/人 |
| outbound_at/by | TEXT | 出库时间/人 |
| returned_quantity | INTEGER | 已归还数量 |
| cancelled_at/by | TEXT | 取消时间/人 |
| revert_reason | TEXT | 撤销原因 |
| reverted_at/by | TEXT | 撤销时间/人 |

### inventory_logs (库存变化日志表)
记录每次库存变化（锁定、解锁、出库、归还、恢复）。

### operation_histories (操作历史表)
记录所有操作及其详情，用于审计追溯。

## 退出码说明
| 退出码 | 说明 |
|--------|------|
| 0 | 成功 |
| 1 | 业务错误（参数错误、数据不存在等） |
| 2 | 权限错误（角色无权操作） |
| 3 | 状态错误（当前状态不允许该操作） |
| 4 | 库存错误（库存不足、超量归还等） |
| 5 | 审计异常（库存审计快照检测到异常） |
| 99 | 系统错误 |

## 数据一致性保证

1. **导出一致性**：导出的 JSON/CSV 数据与当前数据库中的历史记录和库存状态完全一致
2. **幂等导入**：使用 `INSERT OR IGNORE`，同一批次/申请号不会重复导入
3. **事务原子性**：所有涉及多表更新的操作（审批、出库、归还等）均在事务内执行，失败自动回滚
4. **历史不可篡改**：所有操作均追加记录，不更新或删除历史日志
5. **撤销更正库存正确性**：撤销时仅恢复**净出库量**（申请总数量 - 已归还数量），避免重复加回已归还部分；仅 `APPROVED` 状态才解锁锁定库存（出库后 `locked_quantity` 已通过出库操作扣减）

## 库存审计快照验证说明

### 一键运行验证
```bash
# 运行完整审计快照验证测试套件
python test_audit_snapshot.py
```

### 手动验证步骤

#### 1. 跨重启后快照一致性
```bash
# 第一步：创建测试数据并导出快照
python cli.py cb --batch-no B-AUDIT-001 --material 审计物资 --quantity 100 \
  --expiry 2026-12-31 --location 审计仓 --operator warehouse_keeper
python cli.py cr --request-no R-AUDIT-001 --material 审计物资 --quantity 30 \
  --location 安置点 --operator applicant
python cli.py approve --request-id 1 --operator supervisor
python cli.py as --operator supervisor --format json --output ./audit_before.json

# 第二步：重启后再次导出（重新运行 CLI 即为模拟重启）
python cli.py as --operator supervisor --format json --output ./audit_after.json

# 第三步：比较数据一致性（排除快照时间字段）
python -c "
import json
with open('audit_before.json') as f: d1 = json.load(f)
with open('audit_after.json') as f: d2 = json.load(f)
d1.pop('snapshot_at'); d2.pop('snapshot_at')
assert d1 == d2, '跨重启快照不一致'
print('✓ 跨重启后快照数据一致')
"
```

#### 2. JSON/CSV 字段稳定性验证
```bash
# 导出 JSON 并验证字段
python cli.py as --operator supervisor --format json --output ./audit_test.json
python -c "
import json
with open('audit_test.json') as f: d = json.load(f)
required_top = ['snapshot_at','operator','operator_role','filters','summary','materials','anomalies']
required_summary = ['total_materials','total_batches','total_requests','total_quantity','total_locked','total_available','total_logs','total_operations','total_anomalies','critical_anomalies','warning_anomalies']
assert all(k in d for k in required_top), '顶层字段缺失'
assert all(k in d['summary'] for k in required_summary), '汇总字段缺失'
print('✓ JSON 字段结构完整')
"

# 导出 CSV 并验证字段
python cli.py as --operator supervisor --format csv --output ./audit_test
python -c "
import csv
with open('audit_test_materials.csv') as f:
    reader = csv.DictReader(f)
    cols = reader.fieldnames
required = ['material_name','total_quantity','total_locked','total_available','batch_count','request_count','log_count','operation_count']
assert all(c in cols for c in required), 'CSV字段缺失'
print('✓ CSV 字段结构完整')
"
```

#### 3. 导入冲突后审计检测
```bash
# 第一步：创建数据并导出
python cli.py cb --batch-no B-CONFLICT --material 冲突测试物资 --quantity 50 \
  --expiry 2026-12-31 --location A仓 --operator warehouse_keeper
python cli.py cr --request-no R-CONFLICT --material 冲突测试物资 --quantity 10 \
  --location 安置点 --operator applicant
python cli.py export --output ./conflict_export.json --format json

# 第二步：清理后重建数据（制造导入冲突场景）
# 删除 data 目录后重新创建相同批次/申请
python cli.py cb --batch-no B-CONFLICT --material 冲突测试物资 --quantity 50 \
  --expiry 2026-12-31 --location A仓 --operator warehouse_keeper
python cli.py cr --request-no R-CONFLICT --material 冲突测试物资 --quantity 10 \
  --location 安置点 --operator applicant

# 第三步：移除 UNIQUE 约束后导入（模拟导入冲突）
python -c "
import sqlite3, json
conn = sqlite3.connect('data/emergency_supply.db')
c = conn.cursor()
c.executescript('''
    PRAGMA foreign_keys=OFF;
    CREATE TABLE material_batches_new AS SELECT * FROM material_batches WHERE 1=0;
    INSERT INTO material_batches_new SELECT * FROM material_batches;
    DROP TABLE material_batches;
    ALTER TABLE material_batches_new RENAME TO material_batches;
    CREATE TABLE allocation_requests_new AS SELECT * FROM allocation_requests WHERE 1=0;
    INSERT INTO allocation_requests_new SELECT * FROM allocation_requests;
    DROP TABLE allocation_requests;
    ALTER TABLE allocation_requests_new RENAME TO allocation_requests;
    PRAGMA foreign_keys=ON;
''')
conn.commit(); conn.close()
"
python cli.py import --input ./conflict_export.json --format json

# 第四步：审计检测（预期退出码 5，报告批次/申请号冲突）
python cli.py as --operator supervisor
echo "退出码: $?  # 预期为 5"
```

#### 4. 权限越权验证
```bash
# 申请人尝试查看详情（预期失败，退出码 2）
python cli.py as --operator applicant --show-details
echo "退出码: $?  # 预期为 2"

# 申请人导出（脱敏数据）
python cli.py as --operator applicant --format json --output ./applicant_audit.json
python -c "
import json
with open('applicant_audit.json') as f: d = json.load(f)
assert '***' in json.dumps(d), '脱敏标记不存在'
if d['materials'] and d['materials'][0]['batches']:
    assert d['materials'][0]['batches'][0]['location'] == '***', '位置未脱敏'
print('✓ 申请人数据已脱敏')
"

# 无效角色（预期失败，退出码 2）
python cli.py as --operator invalid_role
echo "退出码: $?  # 预期为 2"
```

### 审计快照数据模型

#### AuditSnapshot（审计快照）
```
snapshot_at: 快照时间
operator: 操作人
operator_role: 操作人角色
filters: 筛选条件 {material_name, start_time, end_time}
summary: 汇总统计 {
  total_materials, total_batches, total_requests,
  total_quantity, total_locked, total_available,
  total_logs, total_operations,
  total_anomalies, critical_anomalies, warning_anomalies
}
materials: [
  {
    material_name, total_quantity, total_locked, total_available,
    batches: [BatchSummary],
    requests: [RequestSummary],
    log_count, operation_count
  }
]
anomalies: [AuditAnomaly]
```

#### BatchSummary（批次摘要）
```
batch_id, batch_no, quantity, locked_quantity, available_quantity,
expiry_date, location, created_at, is_expired
```

#### RequestSummary（申请摘要）
```
request_id, request_no, quantity, status, returned_quantity,
created_at, applicant, log_count
```

#### AuditAnomaly（审计异常）
```
anomaly_type, severity (critical/warning),
material_name, entity_id, entity_no, message, details
```
