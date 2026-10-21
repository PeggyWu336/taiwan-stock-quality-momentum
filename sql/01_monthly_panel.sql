-- =========================================================
-- 01_monthly_panel.sql
-- Build the monthly stock panel (monthly_panel) from daily data,
-- then attach yearly free-float ratios.
--
-- Assumes these tables already exist (imported from TEJ):
--   daily_panel, monthly_panel, free_float
--
-- The monthly aggregation block is a per-year template:
-- change the year string and run it once for each year (2005-2025).
-- Two versions are kept below: a 2005 re-run for stock IDs 9000-9999,
-- and the general template (shown with year 2025).
-- =========================================================

-- 2005 re-run for stock IDs 9000-9999: delete old rows first
DELETE FROM monthly_panel
WHERE substr(ym, 1, 4) = '2005'
  AND stock_id BETWEEN '9000' AND '9999';

INSERT INTO monthly_panel (
    stock_id, ym, month_end_date,
    close_eom, mktcap_eom,
    monthly_ret, avg_turnover_m, avg_volume
)
WITH base AS (
    SELECT
        stock_id,
        date_iso,
        mktcap_m,
        turnover_m,
        volume,
        close,
        substr(date_iso, 1, 7) AS ym
    FROM daily_panel
    WHERE substr(date_iso, 1, 4) = '2005'
      AND stock_id BETWEEN '9000' AND '9999'
),
first_last AS (
    SELECT
        stock_id,
        ym,
        MIN(date_iso) AS first_date,
        MAX(date_iso) AS last_date
    FROM base
    GROUP BY stock_id, ym
),
fl_with_price AS (
    SELECT
        f.stock_id,
        f.ym,
        f.first_date,
        f.last_date,
        b1.close    AS first_close,
        b2.close    AS last_close,
        b2.mktcap_m AS mktcap_eom
    FROM first_last f
    LEFT JOIN base b1
      ON f.stock_id = b1.stock_id
     AND f.first_date = b1.date_iso
    LEFT JOIN base b2
      ON f.stock_id = b2.stock_id
     AND f.last_date = b2.date_iso
)
SELECT
    f.stock_id,
    f.ym,
    f.last_date              AS month_end_date,
    f.last_close             AS close_eom,
    f.mktcap_eom,
    CASE
        WHEN f.first_close IS NULL OR f.first_close = 0 THEN NULL
        ELSE (f.last_close * 1.0 / f.first_close) - 1.0
    END                      AS monthly_ret,
    AVG(b.turnover_m)        AS avg_turnover_m,
    AVG(b.volume)            AS avg_volume
FROM fl_with_price f
JOIN base b
  ON f.stock_id = b.stock_id
 AND f.ym = b.ym
GROUP BY
    f.stock_id,
    f.ym,
    f.last_date,
    f.last_close,
    f.mktcap_eom,
    f.first_close;
-- Per-year template: change the year string here, e.g. '2005', '2006', ...
-- All ON / WHERE conditions below follow this year
-- Delete that year's old rows first
DELETE FROM monthly_panel
WHERE substr(ym,1,4) = '2025';

INSERT OR REPLACE INTO monthly_panel (
    stock_id, ym, month_end_date,
    close_eom, mktcap_eom,
    monthly_ret, avg_turnover_m, avg_volume
)
WITH base AS (
    SELECT
        stock_id,
        date_iso,
        mktcap_m,
        turnover_m,
        volume,
        close,
        substr(date_iso, 1, 7) AS ym
    FROM daily_panel
    WHERE substr(date_iso, 1, 4) = '2025'   
),

first_last AS (
    SELECT
        stock_id,
        ym,
        MIN(date_iso) AS first_date,
        MAX(date_iso) AS last_date
    FROM base
    GROUP BY stock_id, ym
),

fl_with_price AS (
    SELECT
        f.stock_id,
        f.ym,
        f.first_date,
        f.last_date,
        b1.close    AS first_close,
        b2.close    AS last_close,
        b2.mktcap_m AS mktcap_eom
    FROM first_last f
    LEFT JOIN base b1
      ON f.stock_id = b1.stock_id
     AND f.first_date = b1.date_iso
    LEFT JOIN base b2
      ON f.stock_id = b2.stock_id
     AND f.last_date = b2.date_iso
)

SELECT
    f.stock_id,
    f.ym,
    f.last_date              AS month_end_date,
    f.last_close             AS close_eom,
    f.mktcap_eom,
    CASE
        WHEN f.first_close IS NULL OR f.first_close = 0
        THEN NULL
        ELSE (f.last_close * 1.0 / f.first_close) - 1.0
    END                      AS monthly_ret,
    AVG(b.turnover_m)        AS avg_turnover_m,
    AVG(b.volume)            AS avg_volume
FROM fl_with_price f
JOIN base b
  ON f.stock_id = b.stock_id
 AND f.ym       = b.ym
GROUP BY
    f.stock_id,
    f.ym,
    f.last_date,
    f.last_close,
    f.mktcap_eom,
    f.first_close;
DROP TABLE IF EXISTS free_float_yearly;

CREATE TABLE free_float_yearly (
    stock_id   TEXT,
    year       TEXT,   -- e.g. '2005'
    free_float REAL    -- precomputed free-float ratio
);

-- 2005
INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2005', "2005/12/30"
FROM free_float;

-- 2006
INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2006', "2006/12/29"
FROM free_float;

-- 2007
INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2007', "2007/12/31"
FROM free_float;

-- 2008
INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2008', "2008/12/31"
FROM free_float;

-- 2009
INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2009', "2009/12/31"
FROM free_float;

INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2010', "2010/12/31"
FROM free_float;

INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2011', "2011/12/30"
FROM free_float;

INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2012', "2012/12/28"
FROM free_float;

INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2013', "2013/12/31"
FROM free_float;

INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2014', "2014/12/31"
FROM free_float;

INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2015', "2015/12/31"
FROM free_float;

INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2016', "2016/12/30"
FROM free_float;

INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2017', "2017/12/29"
FROM free_float;

INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2018', "2018/12/28"
FROM free_float;

INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2019', "2019/12/31"
FROM free_float;

INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2020', "2020/12/31"
FROM free_float;

INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2021', "2021/12/30"
FROM free_float;

INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2022', "2022/12/30"
FROM free_float;

INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2023', "2023/12/29"
FROM free_float;

INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2024', "2024/12/31"
FROM free_float;

INSERT INTO free_float_yearly (stock_id, year, free_float)
SELECT substr(公司代碼, 1, 4), '2025', "2025/12/31"
FROM free_float;

SELECT *
FROM free_float_yearly
ORDER BY stock_id, year
LIMIT 50;

ALTER TABLE monthly_panel ADD COLUMN free_float REAL;

UPDATE monthly_panel
SET free_float = (
    SELECT f.free_float
    FROM free_float_yearly f
    WHERE f.stock_id = monthly_panel.stock_id
      AND f.year = substr(monthly_panel.ym, 1, 4)
);

SELECT stock_id, ym, free_float
FROM monthly_panel
WHERE stock_id='1101'
ORDER BY ym
LIMIT 24;

-- Check free float for a few stocks, 2005-2007
SELECT stock_id, ym, free_float
FROM monthly_panel
WHERE stock_id IN ('1101','1102','2330')
  AND substr(ym,1,4) BETWEEN '2005' AND '2007'
ORDER BY stock_id, ym
LIMIT 60;
-- Check the distribution by year
SELECT
  substr(ym,1,4) AS year,
  COUNT(*)       AS n_obs,
  MIN(free_float) AS min_ff,
  AVG(free_float) AS avg_ff,
  MAX(free_float) AS max_ff
FROM monthly_panel
WHERE free_float IS NOT NULL
GROUP BY substr(ym,1,4)
ORDER BY year;
-- Free-float filter

DROP VIEW IF EXISTS monthly_panel_ff;

CREATE VIEW monthly_panel_ff AS
SELECT *
FROM monthly_panel
WHERE free_float IS NOT NULL
  AND free_float >= 20;   -- threshold: 20% free float

  
  SELECT substr(ym,1,4) AS year,
       COUNT(DISTINCT stock_id) AS n_stocks
FROM monthly_panel_ff
GROUP BY year
ORDER BY year;
