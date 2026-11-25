-- 用途：DISTINCT 掩盖重复
-- 口径：去重后的部门
-- 对账：无
SELECT DISTINCT emp.l1_name
FROM dw_pro.dwd_hr_employee emp
WHERE emp.data_dt = '2026-11-24'
