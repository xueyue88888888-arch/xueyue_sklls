-- 用途：序号分组
-- 口径：按中心
-- 对账：无
SELECT emp.l1_name, COUNT(1) AS cnt
FROM dw_pro.dwd_hr_employee emp
WHERE emp.data_dt = '2026-11-24'
GROUP BY 1
