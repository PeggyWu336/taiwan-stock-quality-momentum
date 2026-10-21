-- =========================================================
-- 02_quarterly_fundamentals.sql
-- Reshape quarterly financial data (fin_quarter_raw, imported from TEJ)
-- and attach the latest available quarter to each month in monthly_panel.
-- Run after 01_monthly_panel.sql.
-- =========================================================

DROP TABLE IF EXISTS fin_quarter_long;

CREATE TABLE fin_quarter_long AS
SELECT
    substr(公司, 1, 4) AS stock_id,          -- e.g. '1101 <company name>' -> '1101'
    年月                      AS date_q_raw,
    NULL                      AS date_q_iso, -- left empty here, filled in the next step
    "ROA(A)稅後息前"          AS roa,
    "稀釋稅後淨利"            AS eps_diluted,
    "負債比率"                AS debt_ratio,
    "流動比率"                AS curr_ratio,
    "來自營運之現金流量"      AS ocf,
    "加權平均股數"            AS shares_wavg,
    "營業毛利率"              AS gross_margin,
    "總資產週轉次數"          AS asset_turnover
FROM fin_quarter_raw;


UPDATE fin_quarter_long
SET date_q_iso = CASE
  -- e.g. 2005/6/30 -> length 9 (YYYY/M/DD)
  WHEN length(date_q_raw) = 9 THEN
       substr(date_q_raw, 1, 4)        || '-' ||   -- year
       '0' || substr(date_q_raw, 6, 1) || '-' ||   -- month, zero-padded
       substr(date_q_raw, 8, 2)                     -- day

  -- e.g. 2005/12/30 -> length 10 (YYYY/MM/DD)
  WHEN length(date_q_raw) = 10 THEN
       substr(date_q_raw, 1, 4)   || '-' ||         -- year
       substr(date_q_raw, 6, 2)   || '-' ||         -- month
       substr(date_q_raw, 9, 2)                      -- day
END;

SELECT stock_id, date_q_raw, date_q_iso
FROM fin_quarter_long
WHERE stock_id = '1101'
ORDER BY date_q_iso
LIMIT 20;

CREATE INDEX IF NOT EXISTS idx_fin_quarter_long
ON fin_quarter_long (stock_id, date_q_iso);


ALTER TABLE monthly_panel ADD COLUMN roa_q            REAL;
ALTER TABLE monthly_panel ADD COLUMN eps_diluted_q    REAL;
ALTER TABLE monthly_panel ADD COLUMN debt_ratio_q     REAL;
ALTER TABLE monthly_panel ADD COLUMN curr_ratio_q     REAL;
ALTER TABLE monthly_panel ADD COLUMN ocf_q            REAL;
ALTER TABLE monthly_panel ADD COLUMN shares_wavg_q    REAL;
ALTER TABLE monthly_panel ADD COLUMN gross_margin_q   REAL;
ALTER TABLE monthly_panel ADD COLUMN asset_turnover_q REAL;

CREATE INDEX IF NOT EXISTS idx_monthly_stockdate
ON monthly_panel (stock_id, month_end_date);

DROP TABLE IF EXISTS month_to_quarter;

CREATE TABLE month_to_quarter AS
SELECT
    m.stock_id,
    m.month_end_date,
    (
        SELECT MAX(f.date_q_iso)
        FROM fin_quarter_long f
        WHERE f.stock_id = m.stock_id
          AND f.date_q_iso <= m.month_end_date
    ) AS date_q_iso
FROM monthly_panel m;

CREATE INDEX idx_m2q_stock ON month_to_quarter(stock_id, month_end_date);


UPDATE monthly_panel
SET
  roa_q = (
      SELECT f.roa
      FROM month_to_quarter mq
      JOIN fin_quarter_long f
           ON f.stock_id = mq.stock_id
          AND f.date_q_iso = mq.date_q_iso
      WHERE mq.stock_id = monthly_panel.stock_id
        AND mq.month_end_date = monthly_panel.month_end_date
  ),
  eps_diluted_q = (
      SELECT f.eps_diluted
      FROM month_to_quarter mq
      JOIN fin_quarter_long f
           ON f.stock_id = mq.stock_id
          AND f.date_q_iso = mq.date_q_iso
      WHERE mq.stock_id = monthly_panel.stock_id
        AND mq.month_end_date = monthly_panel.month_end_date
  ),
  debt_ratio_q = (
      SELECT f.debt_ratio
      FROM month_to_quarter mq
      JOIN fin_quarter_long f
           ON f.stock_id = mq.stock_id
          AND f.date_q_iso = mq.date_q_iso
      WHERE mq.stock_id = monthly_panel.stock_id
        AND mq.month_end_date = monthly_panel.month_end_date
  ),
  curr_ratio_q = (
      SELECT f.curr_ratio
      FROM month_to_quarter mq
      JOIN fin_quarter_long f
           ON f.stock_id = mq.stock_id
          AND f.date_q_iso = mq.date_q_iso
      WHERE mq.stock_id = monthly_panel.stock_id
        AND mq.month_end_date = monthly_panel.month_end_date
  ),
  ocf_q = (
      SELECT f.ocf
      FROM month_to_quarter mq
      JOIN fin_quarter_long f
           ON f.stock_id = mq.stock_id
          AND f.date_q_iso = mq.date_q_iso
      WHERE mq.stock_id = monthly_panel.stock_id
        AND mq.month_end_date = monthly_panel.month_end_date
  ),
  shares_wavg_q = (
      SELECT f.shares_wavg
      FROM month_to_quarter mq
      JOIN fin_quarter_long f
           ON f.stock_id = mq.stock_id
          AND f.date_q_iso = mq.date_q_iso
      WHERE mq.stock_id = monthly_panel.stock_id
        AND mq.month_end_date = monthly_panel.month_end_date
  ),
  gross_margin_q = (
      SELECT f.gross_margin
      FROM month_to_quarter mq
      JOIN fin_quarter_long f
           ON f.stock_id = mq.stock_id
          AND f.date_q_iso = mq.date_q_iso
      WHERE mq.stock_id = monthly_panel.stock_id
        AND mq.month_end_date = monthly_panel.month_end_date
  ),
  asset_turnover_q = (
      SELECT f.asset_turnover
      FROM month_to_quarter mq
      JOIN fin_quarter_long f
           ON f.stock_id = mq.stock_id
          AND f.date_q_iso = mq.date_q_iso
      WHERE mq.stock_id = monthly_panel.stock_id
        AND mq.month_end_date = monthly_panel.month_end_date
  );


SELECT stock_id, ym, month_end_date,
       roa_q, eps_diluted_q, debt_ratio_q, curr_ratio_q
FROM monthly_panel
WHERE stock_id = '1101'
  AND substr(ym,1,4) = '2011'
ORDER BY month_end_date;
