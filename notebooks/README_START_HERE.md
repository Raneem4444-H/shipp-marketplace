# SHIPP P0 Starter Pack

This bundle is intentionally limited to the **current P0 dependency**:

1. Validate Git Folder / Lakehouse access.
2. Build `silver_listings`.
3. Build `silver_requests`.
4. Validate Silver quality.
5. Prepare one OpenRouteService smoke test.
6. Only after Silver is validated, integrate ORS into the real pipeline.

## Run order

```text
notebooks/validation/00_verify_lakehouse_access.ipynb
        ↓
notebooks/development/10_silver_listings_dev.ipynb
        ↓
notebooks/development/11_silver_requests_dev.ipynb
        ↓
notebooks/development/20_ors_smoke_test.ipynb
```

Production modules live under:

```text
data_pipeline/silver/
data_pipeline/ingestion/
config/
```

Do not put secrets in Git.
