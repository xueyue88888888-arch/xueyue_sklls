-- 用途：测试除零
SELECT SUM(hit) * 100.0 / COUNT(*) AS rate FROM t GROUP BY dept
