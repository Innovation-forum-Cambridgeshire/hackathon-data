-- DuckDB starter — the fastest way into this data.
--
--   duckdb < consumers/duckdb.sql
--
-- httpfs lets DuckDB read parquet straight over HTTPS with no download step and no
-- credentials. Swap the LOCAL block for the PUBLISHED block during the event.

INSTALL httpfs; LOAD httpfs;

-- ── LOCAL (while the data subdomain is not up yet) ───────────────────────────
--   python build/build.py build --challenge c03-beyond-the-mainframe \
--       --version v1 --out sample/data/c03-beyond-the-mainframe
CREATE OR REPLACE VIEW cost AS
    SELECT * FROM read_parquet('sample/data/c03-beyond-the-mainframe/gold/workload_cost_daily.parquet');

-- ── PUBLISHED ────────────────────────────────────────────────────────────────
-- CREATE OR REPLACE VIEW cost AS SELECT * FROM read_parquet(
--     'https://data.inno-forum.co.uk/c03-beyond-the-mainframe/v2026-10-26/gold/workload_cost_daily.parquet');
--
-- Use the PINNED version, not /latest/. Judging is against an immutable tag, and a
-- query citing `latest` cannot be reproduced once a newer release lands.

-- 1. What is actually in here. Always the first query.
DESCRIBE cost;
SELECT count(*) AS rows, count(DISTINCT workload_id) AS workloads,
       min(usage_date) AS from_date, max(usage_date) AS to_date
FROM cost;

-- 2. Is the grain what the catalogue claims? A table that is not unique on its
--    stated key inflates every aggregate built on it, and nothing looks wrong.
SELECT count(*) - count(DISTINCT (workload_id, usage_date)) AS duplicate_rows FROM cost;

-- 3. Spend by owner. UNALLOCATED is deliberate — untagged spend is a finding.
SELECT business_unit,
       round(sum(cost_gbp), 2)                              AS cost_gbp,
       round(100 * sum(cost_gbp) / sum(sum(cost_gbp)) OVER (), 1) AS pct_of_total
FROM cost GROUP BY 1 ORDER BY cost_gbp DESC LIMIT 15;

-- 4. Normalise before comparing. Total spend says where the money is; cost per
--    unit says whether it is well spent, and the two often disagree.
SELECT platform,
       round(sum(cost_gbp), 0)                    AS cost_gbp,
       round(sum(vcpu_hours), 0)                  AS vcpu_hours,
       round(sum(cost_gbp) / sum(vcpu_hours), 4)  AS cost_per_vcpu_hour,
       round(avg(utilisation_pct), 1)             AS mean_utilisation_pct
FROM cost GROUP BY 1 ORDER BY cost_per_vcpu_hour DESC;

-- 5. Waste: workloads that cost money and do almost nothing.
SELECT workload_id, platform, business_unit,
       round(sum(cost_gbp), 2)        AS annual_cost_gbp,
       round(avg(utilisation_pct), 1) AS mean_utilisation_pct
FROM cost GROUP BY 1, 2, 3 HAVING avg(utilisation_pct) < 5
ORDER BY annual_cost_gbp DESC LIMIT 20;
