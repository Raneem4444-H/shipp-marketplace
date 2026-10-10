-- SHIPP signup phase S1: durable identity-to-profile bindings.
-- REVIEW ONLY. Execute ONLY after verifying the target is an isolated DEV Lakebase branch.
-- Prerequisite: baseline schema shipp.users exists (user_id VARCHAR(50) PRIMARY KEY).
-- No existing users or roles are altered by this migration.

CREATE TABLE IF NOT EXISTS shipp.user_identities (
    provider VARCHAR(40) NOT NULL,
    issuer TEXT NOT NULL,
    subject TEXT NOT NULL,
    user_id VARCHAR(50) NOT NULL,
    verified_email VARCHAR(320),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_shipp_user_identities
        PRIMARY KEY (provider, issuer, subject),
    CONSTRAINT uq_shipp_user_identities_user
        UNIQUE (user_id),
    CONSTRAINT fk_shipp_user_identities_user
        FOREIGN KEY (user_id)
        REFERENCES shipp.users (user_id)
        ON DELETE RESTRICT,
    CONSTRAINT chk_shipp_identity_provider
        CHECK (length(btrim(provider)) > 0),
    CONSTRAINT chk_shipp_identity_issuer
        CHECK (length(btrim(issuer)) > 0),
    CONSTRAINT chk_shipp_identity_subject
        CHECK (length(btrim(subject)) > 0)
);

COMMENT ON TABLE shipp.user_identities IS
    'Maps verified external identities to existing SHIPP users. Signup must insert the user, roles and binding within one transaction.';
COMMENT ON COLUMN shipp.user_identities.provider IS
    'Authenticated identity provider, e.g. databricks.';
COMMENT ON COLUMN shipp.user_identities.issuer IS
    'Server-configured stable identity authority or workspace identifier; never entered by the user.';
COMMENT ON COLUMN shipp.user_identities.subject IS
    'Stable subject provided by the trusted authentication proxy or OIDC provider; never client-supplied.';
COMMENT ON COLUMN shipp.user_identities.verified_email IS
    'Display/contact attribute from trusted provider; not the authorization key.';

-- Rollback strategy: revert application code first and preserve this table.
-- Do NOT drop this table after users have registered without an approved data migration.
