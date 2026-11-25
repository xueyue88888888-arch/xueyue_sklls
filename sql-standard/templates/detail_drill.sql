-- 用途：KPI 下钻明细（与汇总同源，保证点开后人数一致）
-- 口径：粒度=一行一人；范围与对应 KPI 完全相同的过滤条件
-- 参数：${data_dt} 数据日期，${login_name} 权限账号，${org_id} 机构范围（all=全部）
-- 输出：序号、组织层级、对象属性、状态
-- 对账：本查询行数 = KPI 的“应办人数”
-- 变更：2026-11-25 初版
WITH
scope AS (
    SELECT CAST('${data_dt}' AS DATE) AS data_dt
),
emp_active AS (
    SELECT emp.sys,
           emp.pernr,
           emp.ename,
           emp.l1_name,
           emp.l2_name,
           emp.l3_name
    FROM dw_pro.dwd_hr_employee emp
    CROSS JOIN scope scp
    WHERE emp.data_dt = scp.data_dt
      AND emp.is_active = 1
),
detail AS (
    SELECT emp.*,
           CASE
               WHEN cert.expire_dt IS NULL THEN '无记录'
               WHEN cert.expire_dt <= scp.data_dt THEN '已过期'
               ELSE '正常'
           END AS status
    FROM emp_active emp
    CROSS JOIN scope scp
    LEFT JOIN your_status_cte cert
           ON cert.sys = emp.sys
          AND cert.pernr = emp.pernr
)
SELECT ROW_NUMBER() OVER (ORDER BY det.l1_name, det.pernr) AS seq_no,
       det.l1_name,
       det.l2_name,
       det.l3_name,
       det.pernr,
       det.ename,
       det.status
FROM detail det
ORDER BY seq_no
