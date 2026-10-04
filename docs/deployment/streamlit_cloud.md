# SHIPP on Streamlit Community Cloud

The capstone target remains **Databricks Apps** because the final rubric explicitly
awards deployment points for a working Databricks App. Streamlit Community Cloud is
supported as a public/demo frontend using the same SHIPP code and data contracts.

## Architecture

Streamlit Cloud does not receive Databricks App resource bindings automatically.
Configure a Databricks service principal and Lakebase connection values in Streamlit
Secrets.

The runtime remains:

```text
Streamlit Cloud
  -> Databricks SDK (service principal)
  -> Lakebase
  -> SQL Warehouse / Gold
  -> AI Search
  -> Model Serving
```

Business ownership does not change:

- App writes Listings and Requests.
- Agent writes Saved Items and Agent Activity.
- Lakebase remains operational truth.
- Gold remains trusted candidate eligibility/ranking.
- AI Search remains semantic context.
- Images remain in the Unity Catalog Volume.

## Configure secrets

In Streamlit Community Cloud open:

**App -> Settings -> Secrets**

Use the variable names from:

`.streamlit/secrets.toml.example`

Do not paste secrets into GitHub, notebooks, screenshots, or chat logs.

### Databricks authentication

Preferred external authentication is a dedicated Databricks service principal:

- `DATABRICKS_HOST`
- `DATABRICKS_CLIENT_ID`
- `DATABRICKS_CLIENT_SECRET`

The service principal must have access to the SQL warehouse, AI Search index,
model serving endpoint, UC Volume, and Lakebase credential endpoint required by SHIPP.

### Lakebase

The external app also needs:

- `PGHOST`
- `PGPORT`
- `PGDATABASE`
- `PGUSER`
- `SHIPP_LAKEBASE_ENDPOINT`
- `SHIPP_LAKEBASE_SCHEMA`

The generated Lakebase credential is short-lived. Do not store a static database
password unless a controlled fallback is explicitly required.

## Runtime proof

Open **Deployment & permissions evidence** in the app.

A healthy Streamlit Cloud runtime should show:

- Marketplace config = PASS
- AI Agent config = PASS
- Schema USAGE = PASS
- Required table grants = PASS
- the actual PostgreSQL current_user/session_user

This proves the external runtime is connected correctly.

It does **not** replace the separate final-rubric evidence for a working Databricks App.
Keep Streamlit Cloud as a public demo surface and validate Databricks Apps separately
if the evaluator requires that deployment category.
