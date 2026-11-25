-- 用途：测试 doris 方言
SELECT GROUP_CONCAT(name SEPARATOR ',') FROM t GROUP BY dept
