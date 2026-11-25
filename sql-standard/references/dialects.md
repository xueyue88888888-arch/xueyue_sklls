# 方言差异速查

规则文件：`rules/<方言>.json`。用 `--profile doris` 加载。只写「会报错或会算错」的差异，不写个人偏好。

## Doris

| 事项 | 写法 | 备注 |
|---|---|---|
| GROUP_CONCAT 分隔符 | 不支持 `SEPARATOR`；用 `array_join(collect_list(x), '|')` | 直接报 mismatched input 'SEPARATOR' |
| 日期加减 | `DATE_ADD(dt, INTERVAL n DAY)` | 与 MySQL 一致 |
| 分页 | `LIMIT n OFFSET m` | 逗号写法语义易反 |
| 空安全比较 | `<=>` 可用；`ISNULL(x)` 与 MySQL 含义不同 | 谓词统一用 `x IS NULL` |
| 分区裁剪 | 别对 `data_dt` 套 `DATE_FORMAT`/`SUBSTR`，改区间比较 | 套函数失去裁剪，退化成全表扫 |
| 数组/JSON | 有 `collect_list`、`array_join`，无 `string_agg` | |
| 窗口 | `ROW_NUMBER/SUM` 全支持 | |
| CTE | 支持 `WITH`，但**不要在 CTE 里再嵌套过多层**，部分版本对深层 CTE 优化差 | |

## MySQL

| 事项 | 写法 |
|---|---|
| GROUP_CONCAT | `GROUP_CONCAT(x SEPARATOR '|')` |
| 空安全等于 | `<=>` |
| 集合查找 | `FIND_IN_SET(x, 'a,b,c')` |
| 日期加减 | `DATE_ADD(dt, INTERVAL n DAY)` |

## PostgreSQL

| 事项 | 写法 |
|---|---|
| 拼接 | `a || b`，或 `concat()`（注意 NULL：concat 忽略 NULL，|| 遇 NULL 变 NULL） |
| 取每组第一条 | `DISTINCT ON (key) ... ORDER BY key, t DESC` |
| 类型转换 | `x::date` |
| 空安全比较 | `IS DISTINCT FROM` |

## 跨方言通用红线

- 除法一律 `NULLIF(分母, 0)`
- 字符串比较前 `TRIM`
- 日期字面量不要写死，用参数
- 不用 `SELECT *`
