-- 用途：写死日期
-- 口径：单日
-- 对账：无
SELECT COUNT(1) AS cnt
FROM dw_pro.dwd_hr_employee emp
WHERE emp.data_dt = DATE '2026-11-24'
