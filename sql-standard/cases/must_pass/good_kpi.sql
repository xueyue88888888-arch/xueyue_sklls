-- 用途：按部门统计健康证异常占比（示例，符合交付规范）
-- 口径：粒度=中心；范围=当日在职（active=1）；异常=无证或已过期
-- 参数：${data_dt} 数据日期，${org_id} 机构范围（all=全部）
-- 输出：中心名称、应办人数、异常人数、异常占比（%）
-- 对账：SUM(应办人数) 应等于同口径人员总数
-- 变更：2026-11-25 初版
WITH
scope AS (
    SELECT data_dt FROM (SELECT MAX(data_dt) AS data_dt FROM dw_pro.dwd_hr_employee) x
),
emp_active AS (
    SELECT emp.sys, emp.pernr, emp.l1_name
    FROM dw_pro.dwd_hr_employee emp
    CROSS JOIN scope scp
    WHERE emp.data_dt = scp.data_dt
      AND emp.is_active = 1
),
cert_latest AS (
    SELECT sys, pernr, expire_dt
    FROM (
        SELECT crt.sys,
               crt.pernr,
               crt.expire_dt,
               ROW_NUMBER() OVER (
                   PARTITION BY crt.sys, crt.pernr
                   ORDER BY crt.aedtm DESC, crt.begda DESC, crt.endda DESC, crt.seqnr DESC
               ) AS rn
        FROM (
            SELECT 'ecc' AS sys, TRIM(PERNR) AS pernr, USETO AS expire_dt,
                   AEDTM AS aedtm, BEGDA AS begda, ENDDA AS endda, TRIM(SEQNR) AS seqnr
            FROM dw_pro.ODS_ECC_HR_PA0185
            WHERE ICTYP = '02' AND TRIM(SEQNR) = '000'
            UNION ALL
            SELECT 'rt', TRIM(PERNR), USETO, AEDTM, BEGDA, ENDDA, TRIM(SEQNR)
            FROM dw_pro.ODS_RT_HR_PA0185
            WHERE ICTYP = '02' AND TRIM(SEQNR) = '000'
        ) crt
    ) ranked
    WHERE ranked.rn = 1
),
result AS (
    SELECT emp.l1_name AS center_name,
           COUNT(1) AS should_cnt,
           SUM(CASE
                   WHEN cert.expire_dt IS NULL OR cert.expire_dt <= scp.data_dt THEN 1
                   ELSE 0
               END) AS abnormal_cnt
    FROM emp_active emp
    LEFT JOIN cert_latest cert
           ON cert.sys = emp.sys
          AND cert.pernr = emp.pernr
    CROSS JOIN scope scp
    GROUP BY emp.l1_name
)
SELECT center_name,
       should_cnt,
       abnormal_cnt,
       ROUND(abnormal_cnt * 100.0 / NULLIF(should_cnt, 0), 2) AS abnormal_pct
FROM result
ORDER BY should_cnt DESC
LIMIT 200
