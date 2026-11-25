-- 用途：分区字段套函数
-- 口径：按月
-- 对账：无
SELECT DATE_FORMAT(emp.data_dt, '%Y-%m') AS ym, COUNT(1) AS cnt
FROM dw_pro.dwd_hr_employee emp
WHERE emp.is_active = 1
GROUP BY DATE_FORMAT(emp.data_dt, '%Y-%m')
