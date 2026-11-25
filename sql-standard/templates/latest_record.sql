-- 用途：取每个对象（人员/门店/单据）最新一条生效记录
-- 口径：粒度=对象一条；范围=截至 ${data_dt} 生效（begda<=当日<=endda）且已录入（aedtm<=当日）
-- 参数：${data_dt} 数据日期，${src} 事实表
-- 输出：对象键 + 业务列（每对象仅 1 行）
-- 对账：SELECT COUNT(1)=COUNT(DISTINCT 对象键) 必须成立
-- 变更：2026-11-25 初版
WITH
scope AS (
    SELECT CAST('${data_dt}' AS DATE) AS data_dt
),
base AS (
    SELECT src.obj_key,
           src.business_col,
           src.begda,
           src.endda,
           src.aedtm,
           src.seqnr
    FROM your_source_table src
    CROSS JOIN scope scp
    WHERE src.begda <= scp.data_dt
      AND src.endda >= scp.data_dt
      AND src.aedtm <= scp.data_dt
),
ranked AS (
    SELECT base.obj_key,
           base.business_col,
           ROW_NUMBER() OVER (
               PARTITION BY base.obj_key
               ORDER BY base.aedtm DESC, base.begda DESC, base.endda DESC, base.seqnr DESC
           ) AS rn
    FROM base
)
SELECT obj_key,
       business_col
FROM ranked
WHERE rn = 1
