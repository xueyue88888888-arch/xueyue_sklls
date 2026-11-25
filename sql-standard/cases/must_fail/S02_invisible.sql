-- 用途：测试隐藏字符
SELECT * FROM t WHERE dept_id NOT IN ('__ALL​__')
