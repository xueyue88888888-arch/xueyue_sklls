-- 用途：测试 NOT IN
SELECT * FROM t WHERE dept_id NOT IN (SELECT dept_id FROM black_list)
