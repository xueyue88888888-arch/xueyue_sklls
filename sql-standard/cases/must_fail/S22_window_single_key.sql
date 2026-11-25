-- 用途：窗口单排序键
-- 口径：每人最新
-- 对账：无
SELECT crt.pernr, crt.expire_dt
FROM (
    SELECT PERNR AS pernr,
           USETO AS expire_dt,
           ROW_NUMBER() OVER (PARTITION BY PERNR ORDER BY AEDTM DESC) AS rn
    FROM dw_pro.ODS_ECC_HR_PA0185
    WHERE ICTYP = '02' AND AEDTM <= '2026-11-24'
) crt
WHERE crt.rn = 1
