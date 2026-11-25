-- 用途：数仓表无日期条件
-- 口径：全部在职
-- 对账：无
SELECT emp.pernr
FROM dw_pro.dwd_hr_employee emp
WHERE emp.is_active = 1
