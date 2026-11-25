-- 用途：ISNULL 当谓词
-- 口径：无证人员
-- 对账：无
SELECT emp.pernr
FROM dw_pro.dwd_hr_employee emp
WHERE emp.data_dt = '2026-11-24' AND ISNULL(emp.resign_dt)
