-- 用途：LIMIT 逗号写法
-- 口径：全部
-- 对账：无
SELECT emp.pernr
FROM dw_pro.dwd_hr_employee emp
WHERE emp.data_dt = '2026-11-24'
LIMIT 10, 20
