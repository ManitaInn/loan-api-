-- Runs once, the first time the Postgres container starts with an empty volume.
CREATE TABLE IF NOT EXISTS predictions (
    id                  SERIAL PRIMARY KEY,
    amount_usd          NUMERIC(12, 2) NOT NULL,
    term_months         INTEGER        NOT NULL,
    monthly_income_usd  NUMERIC(12, 2) NOT NULL,
    age                 INTEGER        NOT NULL,
    existing_loans      INTEGER        NOT NULL,
    default_probability NUMERIC(6, 4)  NOT NULL,
    approved            BOOLEAN        NOT NULL,
    created_at          TIMESTAMPTZ    NOT NULL DEFAULT now()
);
