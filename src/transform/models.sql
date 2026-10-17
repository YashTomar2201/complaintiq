-- Clean tables and views. Rules come from docs/data-profile.md.
-- Source: raw_complaints (all VARCHAR, blanks already NULL). Rebuilt from scratch on every run.

CREATE OR REPLACE TABLE complaints AS
WITH base AS (
SELECT
    complaint_id,

    -- dates: proper DATE type, plus helper columns for grouping
    CAST(date_received AS DATE)                              AS date_received,
    strftime(CAST(date_received AS DATE), '%Y-%m')           AS year_month,
    CAST(date_trunc('week', CAST(date_received AS DATE)) AS DATE) AS week,
    CAST(date_sent_to_company AS DATE)                       AS date_sent_to_company,

    -- text standardisation: trim + collapse repeated spaces (casing is already consistent in the source)
    trim(regexp_replace(product, '\s+', ' ', 'g'))           AS product,
    CASE WHEN sub_product IS NULL OR lower(trim(sub_product)) = 'i do not know' THEN NULL
         ELSE trim(regexp_replace(sub_product, '\s+', ' ', 'g')) END AS sub_product,
    trim(regexp_replace(issue, '\s+', ' ', 'g'))             AS issue,
    trim(regexp_replace(sub_issue, '\s+', ' ', 'g'))         AS sub_issue,

    -- narrative: line breaks and repeated spaces collapsed to single spaces
    nullif(trim(regexp_replace(consumer_complaint_narrative, '\s+', ' ', 'g')), '') AS narrative,
    nullif(trim(consumer_complaint_narrative), '') IS NOT NULL AS has_narrative,

    -- location: ZIP stays TEXT. CFPB masks some ZIPs ('604XX'), so keep three views of it
    upper(trim(state))                                       AS state,
    CASE WHEN regexp_matches(zip_code, '^[0-9]{5}$') THEN zip_code END AS zip5,       -- full ZIP only
    CASE WHEN regexp_matches(zip_code, '^[0-9]{3}') THEN substr(zip_code, 1, 3) END AS zip3, -- usable prefix
    coalesce(zip_code LIKE '%X%', FALSE)                     AS zip_masked,

    -- tags -> booleans
    coalesce(tags LIKE '%Older American%', FALSE)            AS is_older_american,
    coalesce(tags LIKE '%Servicemember%', FALSE)             AS is_servicemember,

    submitted_via,

    -- response fields
    (timely = 'Yes')                                         AS timely,
    company_response,
    (company_response <> 'In progress')                      AS is_final_response,
    (company_response = 'Closed with monetary relief')       AS got_monetary_relief,
    (company_response IN ('Closed with monetary relief', 'Closed with non-monetary relief')) AS got_any_relief,
    source,
    -- TRUE when the newest bulk file no longer lists this complaint (e.g. 55 'In progress' ones from Jul-Aug 2026)
    coalesce(missing_from_bulk, FALSE)                       AS missing_from_bulk
FROM raw_complaints
)
SELECT
    base.*,

    -- narrative helpers for the AI phases
    length(narrative)                                        AS narrative_chars,
    -- dollar amounts the CFPB wraps in braces, e.g. '{$123.45}' -> 123.45 (rule-based cross-check for the LLM)
    list_transform(regexp_extract_all(narrative, '\{\$([0-9,]+(?:\.[0-9]+)?)\}', 1),
                   x -> CAST(replace(x, ',', '') AS DOUBLE)) AS amounts_usd,
    -- identical narrative text appears many times (one template: 576 copies). Different customers, so they
    -- stay in analytics, but AI sampling and the gold set should use only `is_first_copy`.
    count(*) FILTER (WHERE narrative IS NOT NULL) OVER (PARTITION BY narrative) AS narrative_copies,
    (narrative IS NOT NULL
        AND row_number() OVER (PARTITION BY narrative ORDER BY date_received, complaint_id) = 1) AS is_first_copy
FROM base;

-- Complaints per month per product (dashboard trends)
CREATE OR REPLACE VIEW v_monthly_trends AS
SELECT year_month, product, count(*) AS complaints
FROM complaints
GROUP BY year_month, product;

-- On-time response % per month per product
CREATE OR REPLACE VIEW v_timeliness AS
SELECT year_month, product,
       count(*)                                  AS complaints,
       count(*) FILTER (WHERE timely)            AS timely_complaints,
       round(100.0 * count(*) FILTER (WHERE timely) / count(*), 2) AS timely_pct
FROM complaints
GROUP BY year_month, product;
