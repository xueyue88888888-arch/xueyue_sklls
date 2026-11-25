-- 用途：测试表别名
SELECT e.name FROM dw_pro.dwd_hr_employee e JOIN dw_pro.dim_hr_org o ON o.dept_id = e.dept
