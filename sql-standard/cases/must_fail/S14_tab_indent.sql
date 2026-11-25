-- 用途：tab 缩进
-- 口径：无
-- 对账：无
SELECT emp.pernr
FROM dw_pro.dwd_hr_employee emp
WHERE emp.data_dt = '2026-11-24'
	AND emp.is_active = 1
