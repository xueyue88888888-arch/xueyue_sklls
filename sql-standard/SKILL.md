---
name: sql-standard
description: SQL 交付规范与质量门禁（数据治理级，通用不绑库表）。当需要写、改、评审、交付任何 SQL 时使用——报表数据集、下钻明细、跑批脚本、临时取数都算。交付前必须通过 sqlguard 检查，P0 未清零不许交付。
---

# SQL 交付规范（数据治理级）

一套**与库表无关**的 SQL 标准：规范文档管「该写成什么样」，检查器管「能机械判的部分」，模板管「高频结构照着填就别出错」。落到具体客户时再挂项目字典，标准和项目资产分开。

## 什么时候用这个 skill

- 要写新 SQL（数据集、下钻、跑批、取数）
- 要改别人的 SQL / 修数 / 加字段
- 要评审一段 AI 生成的 SQL
- 报表上线前自检

## 五条铁律

1. **先选模板，不写空白页**。KPI 汇总、明细下钻、取最新一条、时间段对比——这四个坑 90% 的错都在这，模板里已经避开了。
2. **每条交付 SQL 都有头注释**：用途 / 口径 / 参数 / 输出 / 对账 / 变更。缺一项就不算交付。
3. **写完必须跑检查器**：P0 清零才算完，不许「看起来对」就交。
4. **汇总和明细同源**：共用同一套 CTE，交付前跑一次「明细行数 = KPI 人数」，把数字写进注释。
5. **报错必须给修法**：检查器每条问题都带「修：」，照抄就能改。

## 标准流程

```
1. 认口径     → 粒度是什么？范围怎么定？异常怎么算？（写不出就别写 SQL）
2. 挑模板     → templates/ 里找最接近的，复制一份改
3. 写结构     → 参数 → 口径 → 事实 → 结果，四段 CTE
4. 补头注释   → references/delivery.md 的模板
5. 跑检查     → python bin/sqlguard.py check your.sql --profile <方言>
6. 修到 P0=0  → 照着「修：」改
7. 试跑对账   → LIMIT 10 跑通；总数 = 分组和；KPI = 明细行数
```

## 命令

```bash
# 检查一个文件（通用规则）
python bin/sqlguard.py check sql/x.sql

# 带方言规则（doris / mysql / postgres）
python bin/sqlguard.py check sql/x.sql --profile doris

# 从标准输入读（复制粘贴场景）
pbpaste | python bin/sqlguard.py check - --profile doris

# 机器可读
python bin/sqlguard.py check sql/x.sql --profile doris --json

# 列出规则
python bin/sqlguard.py rules --profile doris

# 规则自测（改了规则必须跑）
python bin/selftest.py
```

退出码：`0` 通过 / `1` 有 P0 / `2` 用法错误。可直接接 pre-commit 或 CI。
输出：控制台用系统编码（Windows 中文环境不乱码），重定向到文件时自动用 UTF-8。

## 分级与判定

| 级别 | 含义 | 是否阻断 |
|---|---|---|
| P0 | 会算错数、少数据、跑挂 | 阻断，必须清零 |
| P1 | 可读性与可维护性 | 提示，交付前尽量清零 |
| P2 | 风险提醒（性能、稳定性） | 提示，按场景判断 |

风格分（结构/命名/可读/正确四个维度）**只用于观察趋势，不参与判定**。原因：让人或模型给 SQL 打个总分是假精确，真判断只有「P0 有没有」。

## 目录

```
sql-standard/
  SKILL.md                  ← 你在读的这份
  references/
    standard.md             ← 完整规范：结构/命名/可读/正确/性能/方言/交付
    delivery.md             ← 交付契约：头注释 + 三段验收 + 汇总明细同源
    dialects.md             ← Doris / MySQL / PG 差异速查
  rules/
    common.json             ← 17 条通用规则（不绑库）
    doris.json              ← 4 条 Doris 方言规则（合计 21 条）
    mysql.json              ← 需要时再补，格式同 doris.json
  templates/
    kpi_summary.sql         ← KPI 汇总（带对账）
    detail_drill.sql        ← 明细下钻（与汇总同源）
    latest_record.sql       ← 取每人最新一条生效记录
  cases/
    must_fail/              ← 每条规则一个反例（21 条全覆盖）
    must_pass/              ← 必须 0 个 P0 的正例
  bin/
    sqlguard.py             ← 检查器（零依赖，Python 3.8+）
    selftest.py             ← 规则自测
```

## 怎么加规则

规则是数据，不是代码。改 `rules/*.json`：

```json
{
  "id": "S31",
  "level": "P0",
  "title": "一句话说清问题",
  "type": "regex",
  "pattern": "正则，跑在去掉注释和字符串内容后的代码区",
  "fix": "照着就能改的具体写法",
  "why": "为什么这算错——写给三个月后的自己看"
}
```

结构性检查（不是单条正则能表达的）用 `"type": "custom"` + `"check": "函数名"`，在 `sqlguard.py` 的 `CUSTOM` 表里实现。

**加规则必做两件事**：
1. `cases/must_fail/<规则ID>_名字.sql` 放一个反例；
2. 跑 `python bin/selftest.py`，确认这条规则命中了，别的规则没被误杀。

规则空转（写了但从不命中）和规则误杀（把正确 SQL 判错）都算 bug。

## 禁用的写法（为什么不做）

- **不让模型给 SQL 打分当门禁**。打分不稳定、不可复现，还会掩盖真问题。判定只看 P0。
- **不写「最佳实践」式的模糊条款**。每条要么能被机器判，要么能在评审时一句话回答是/否。
- **不做全量 SQL 解析器**。用「去注释去字符串后的正则 + 少量结构检查」，够用且不会因为一个方言怪语法就崩。

## 挂项目资产（可选，进阶）

通用规则不知道你库里有哪张表、哪个字段。要让检查器认识你的库，加一层项目字典：

```
project-meta/
  tables.json      ← {表名: {comment, cols:{列名: 注释}, partition:"data_dt"}}
  sentinels.json   ← 哨兵值清单
  enums.json       ← 枚举字段与取值范围
```

有了字典，「字段不存在」「枚举值写错」「表没有这个分区」这类错也能机械判。字典从 `information_schema` 导一次即可，属于项目层，不进这个 skill 本体。
