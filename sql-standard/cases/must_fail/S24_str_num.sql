-- 用途：编码与数字比较
-- 口径：单部门
-- 对账：无
SELECT emp.pernr
FROM dw_pro.dwd_hr_employee emp
WHERE emp.data_dt = '2026-11-24'
  AND emp.l2_id = 1893
