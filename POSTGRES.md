# Table info for our Postgres db

## Company facts

```
CREATE TABLE IF NOT EXISTS company_facts (
    cik TEXT PRIMARY KEY,
    sic TEXT,
    sic_description TEXT,
    owner_org TEXT,
    entity_name TEXT,
    tickers TEXT[],
    exchanges TEXT[],
    ein TEXT,
    description TEXT,
    website TEXT,
    category TEXT,
    state_of_incorporation TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trigger to update last_updated on any change
CREATE OR REPLACE FUNCTION update_last_updated_column()
RETURNS TRIGGER AS $$
BEGIN
   NEW.last_updated = CURRENT_TIMESTAMP;
   RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_company_facts_last_updated
BEFORE UPDATE ON company_facts
FOR EACH ROW EXECUTE FUNCTION update_last_updated_column();
```


## Company filings

```
CREATE TABLE company_filings (
    id SERIAL PRIMARY KEY,
    cik TEXT NOT NULL,
    form TEXT NOT NULL,
    filing_date DATE,
    accession_number TEXT NOT NULL,
    primary_doc TEXT,
    archive_url TEXT,
    sentiment TEXT,
    processed BOOLEAN DEFAULT FALSE,
    UNIQUE (cik, accession_number)
);

-- Add indexes for improved query performance
CREATE INDEX idx_company_filings_cik ON company_filings (cik);
CREATE INDEX idx_company_filings_processed ON company_filings (processed);
CREATE INDEX idx_company_filings_sentiment ON company_filings (sentiment);
```

## Vector embeddings for filings

```
CREATE TABLE filing_embedding_chunks (
    id SERIAL PRIMARY KEY,
    filing_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    embedding VECTOR(1536) NOT NULL,
    FOREIGN KEY (filing_id) REFERENCES company_filings(id) ON DELETE CASCADE,
    UNIQUE (filing_id, chunk_index)
);
```