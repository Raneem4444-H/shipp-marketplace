/*shipp lakebase schema · SQL*/
/*
 * SHIPP Marketplace - Lakebase Operational Database Schema
 * Platform: Databricks Lakebase (PostgreSQL-compatible)
 * Purpose: Operational transactional database for user management, listings, requests, and matching
 *
 * Issue #1 fix: every object below is fully schema-qualified (bootcamp_shipp.*).
 * This script no longer depends on the session's search_path to resolve correctly.
 */
-- ============================================================================
-- 1. ROLES TABLE - User role definitions
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS bootcamp_shipp;
CREATE TABLE IF NOT EXISTS bootcamp_shipp.roles (
    role_id VARCHAR(50) PRIMARY KEY,
    role_name VARCHAR(100) NOT NULL,
    CONSTRAINT uk_role_name UNIQUE(role_name),
    CONSTRAINT chk_valid_roles CHECK(
        role_name IN ('DONOR', 'REQUESTER', 'SHIPPING_PARTNER')
    )
);
COMMENT ON TABLE bootcamp_shipp.roles IS 'Defines available user roles in the SHIPP platform';
COMMENT ON COLUMN bootcamp_shipp.roles.role_id IS 'Unique role identifier (e.g., DONOR, REQUESTER, SHIPPING_PARTNER)';
COMMENT ON COLUMN bootcamp_shipp.roles.role_name IS 'Human-readable role name with business meaning';
-- ============================================================================
-- 2. USERS TABLE - Core user entity
-- ============================================================================
-- test File It will be delete soon 
CREATE TABLE IF NOT EXISTS bootcamp_shipp.users (
    user_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    current_city VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);
COMMENT ON TABLE bootcamp_shipp.users IS 'Core user entity for all platform participants (donors, requesters, shipping partners)';
COMMENT ON COLUMN bootcamp_shipp.users.user_id IS 'Unique user identifier (UUID or username)';
COMMENT ON COLUMN bootcamp_shipp.users.name IS 'User display name';
COMMENT ON COLUMN bootcamp_shipp.users.current_city IS 'Current city where user is located (e.g., Abu Dhabi)';
COMMENT ON COLUMN bootcamp_shipp.users.created_at IS 'Account creation timestamp';
COMMENT ON COLUMN bootcamp_shipp.users.updated_at IS 'Last profile update timestamp';
COMMENT ON COLUMN bootcamp_shipp.users.is_active IS 'Account active/inactive status for soft deletes';
CREATE INDEX idx_users_city ON bootcamp_shipp.users(current_city);
CREATE INDEX idx_users_active ON bootcamp_shipp.users(is_active);
-- ============================================================================
-- 3. USER_ROLES TABLE - User-to-Role mapping (junction table)
-- ============================================================================
CREATE TABLE IF NOT EXISTS bootcamp_shipp.user_roles (
    user_id VARCHAR(50) NOT NULL,
    role_id VARCHAR(50) NOT NULL,
    assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    assigned_by VARCHAR(50),
    PRIMARY KEY (user_id, role_id),
    FOREIGN KEY (user_id) REFERENCES bootcamp_shipp.users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES bootcamp_shipp.roles(role_id) ON DELETE RESTRICT
);
COMMENT ON TABLE bootcamp_shipp.user_roles IS 'Maps users to roles (many-to-many relationship for multi-role support)';
COMMENT ON COLUMN bootcamp_shipp.user_roles.user_id IS 'Reference to user';
COMMENT ON COLUMN bootcamp_shipp.user_roles.role_id IS 'Reference to role';
COMMENT ON COLUMN bootcamp_shipp.user_roles.assigned_at IS 'When the role was assigned to the user';
COMMENT ON COLUMN bootcamp_shipp.user_roles.assigned_by IS 'Admin user who assigned this role (if applicable)';
CREATE INDEX idx_user_roles_user ON bootcamp_shipp.user_roles(user_id);
CREATE INDEX idx_user_roles_role ON bootcamp_shipp.user_roles(role_id);
-- ============================================================================
-- 4. LISTINGS TABLE - Donor item postings
-- ============================================================================
CREATE TABLE IF NOT EXISTS bootcamp_shipp.listings (
    listing_id VARCHAR(50) PRIMARY KEY,
    donor_id VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    condition VARCHAR(50),
    location VARCHAR(255),
    latitude FLOAT,
    longitude FLOAT,
    available_from TIMESTAMP,
    available_until TIMESTAMP,
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (donor_id) REFERENCES bootcamp_shipp.users(user_id) ON DELETE CASCADE,
    CONSTRAINT chk_listing_status CHECK(
        status IN (
            'ACTIVE',
            'MATCHED',
            'RESERVED',
            'ARCHIVED',
            'EXPIRED'
        )
    )
);
COMMENT ON TABLE bootcamp_shipp.listings IS 'Items available for donation posted by donors';
COMMENT ON COLUMN bootcamp_shipp.listings.listing_id IS 'Unique listing identifier';
COMMENT ON COLUMN bootcamp_shipp.listings.donor_id IS 'Foreign key to users table (who is donating)';
COMMENT ON COLUMN bootcamp_shipp.listings.title IS 'Item title/name';
COMMENT ON COLUMN bootcamp_shipp.listings.description IS 'Detailed item description, condition notes, pickup instructions';
COMMENT ON COLUMN bootcamp_shipp.listings.category IS 'Item category (e.g., Furniture, Electronics, Books, Kitchen, Clothing)';
COMMENT ON COLUMN bootcamp_shipp.listings.condition IS 'Item condition (e.g., Like New, Good, Fair, Used)';
COMMENT ON COLUMN bootcamp_shipp.listings.location IS 'Pickup location address';
COMMENT ON COLUMN bootcamp_shipp.listings.latitude IS 'Geographic latitude for location-based matching';
COMMENT ON COLUMN bootcamp_shipp.listings.longitude IS 'Geographic longitude for location-based matching';
COMMENT ON COLUMN bootcamp_shipp.listings.available_from IS 'When the item becomes available for pickup';
COMMENT ON COLUMN bootcamp_shipp.listings.available_until IS 'When the item is no longer available (expiry/deadline)';
COMMENT ON COLUMN bootcamp_shipp.listings.status IS 'Listing lifecycle status';
CREATE INDEX idx_listings_donor ON bootcamp_shipp.listings(donor_id);
CREATE INDEX idx_listings_status ON bootcamp_shipp.listings(status);
CREATE INDEX idx_listings_category ON bootcamp_shipp.listings(category);
CREATE INDEX idx_listings_location ON bootcamp_shipp.listings(latitude, longitude);
CREATE INDEX idx_listings_available ON bootcamp_shipp.listings(available_from, available_until);
-- ============================================================================
-- 5. LISTING_FILES TABLE - Images and documents for listings
-- ============================================================================
CREATE TABLE IF NOT EXISTS bootcamp_shipp.listing_files (
    listing_file_id VARCHAR(50) PRIMARY KEY,
    listing_id VARCHAR(50) NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    file_type VARCHAR(50),
    file_size BIGINT,
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (listing_id) REFERENCES bootcamp_shipp.listings(listing_id) ON DELETE CASCADE
);
COMMENT ON TABLE bootcamp_shipp.listing_files IS 'Images and documents attached to listings (photos, condition documentation)';
COMMENT ON COLUMN bootcamp_shipp.listing_files.listing_file_id IS 'Unique file identifier';
COMMENT ON COLUMN bootcamp_shipp.listing_files.listing_id IS 'Reference to parent listing';
COMMENT ON COLUMN bootcamp_shipp.listing_files.file_path IS 'Path/URI to file in DBFS or cloud storage (s3://, gs://, etc.)';
COMMENT ON COLUMN bootcamp_shipp.listing_files.file_type IS 'File MIME type (image/jpeg, image/png, application/pdf, etc.)';
COMMENT ON COLUMN bootcamp_shipp.listing_files.file_size IS 'File size in bytes';
COMMENT ON COLUMN bootcamp_shipp.listing_files.uploaded_at IS 'File upload timestamp';
CREATE INDEX idx_listing_files_listing ON bootcamp_shipp.listing_files(listing_id);
-- ============================================================================
-- 6. REQUESTS TABLE - Requester needs/requests
-- ============================================================================
CREATE TABLE IF NOT EXISTS bootcamp_shipp.requests (
    request_id VARCHAR(50) PRIMARY KEY,
    requester_id VARCHAR(50) NOT NULL,
    request_text TEXT NOT NULL,
    category VARCHAR(100),
    location VARCHAR(255),
    latitude FLOAT,
    longitude FLOAT,
    need_by_date TIMESTAMP,
    status VARCHAR(50) NOT NULL DEFAULT 'OPEN',
    priority VARCHAR(50) DEFAULT 'MEDIUM',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (requester_id) REFERENCES bootcamp_shipp.users(user_id) ON DELETE CASCADE,
    CONSTRAINT chk_request_status CHECK(
        status IN (
            'OPEN',
            'PENDING',
            'MATCHED',
            'FULFILLED',
            'CANCELLED'
        )
    ),
    CONSTRAINT chk_priority CHECK(priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT'))
);
COMMENT ON TABLE bootcamp_shipp.requests IS 'Needs/requests posted by requesters looking for items';
COMMENT ON COLUMN bootcamp_shipp.requests.request_id IS 'Unique request identifier';
COMMENT ON COLUMN bootcamp_shipp.requests.requester_id IS 'Foreign key to users table (who is requesting)';
COMMENT ON COLUMN bootcamp_shipp.requests.request_text IS 'Description of what is needed';
COMMENT ON COLUMN bootcamp_shipp.requests.category IS 'Category of needed item (should align with listing categories)';
COMMENT ON COLUMN bootcamp_shipp.requests.location IS 'Desired delivery/pickup location address';
COMMENT ON COLUMN bootcamp_shipp.requests.latitude IS 'Geographic latitude for location-based matching';
COMMENT ON COLUMN bootcamp_shipp.requests.longitude IS 'Geographic longitude for location-based matching';
COMMENT ON COLUMN bootcamp_shipp.requests.need_by_date IS 'Deadline for fulfilling the request';
COMMENT ON COLUMN bootcamp_shipp.requests.status IS 'Request lifecycle status';
COMMENT ON COLUMN bootcamp_shipp.requests.priority IS 'Request priority for matching algorithm';
CREATE INDEX idx_requests_requester ON bootcamp_shipp.requests(requester_id);
CREATE INDEX idx_requests_status ON bootcamp_shipp.requests(status);
CREATE INDEX idx_requests_category ON bootcamp_shipp.requests(category);
CREATE INDEX idx_requests_location ON bootcamp_shipp.requests(latitude, longitude);
CREATE INDEX idx_requests_need_by_date ON bootcamp_shipp.requests(need_by_date);
-- ============================================================================
-- 7. SAVED_ITEMS TABLE - Matching/pairing between requests and listings
-- ============================================================================
CREATE TABLE IF NOT EXISTS bootcamp_shipp.saved_items (
    saved_item_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    request_id VARCHAR(50),
    listing_id VARCHAR(50),
    match_score FLOAT,
    match_reason VARCHAR(255),
    saved_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'SAVED',
    FOREIGN KEY (user_id) REFERENCES bootcamp_shipp.users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (request_id) REFERENCES bootcamp_shipp.requests(request_id) ON DELETE
    SET NULL,
        FOREIGN KEY (listing_id) REFERENCES bootcamp_shipp.listings(listing_id) ON DELETE
    SET NULL,
        CONSTRAINT chk_saved_item_status CHECK(
            status IN ('SAVED', 'ACCEPTED', 'REJECTED', 'COMPLETED')
        ),
        CONSTRAINT chk_saved_pair CHECK(
            request_id IS NOT NULL
            OR listing_id IS NOT NULL
        )
);
COMMENT ON TABLE bootcamp_shipp.saved_items IS 'Matches between requests and listings (core business logic: who saved what match)';
COMMENT ON COLUMN bootcamp_shipp.saved_items.saved_item_id IS 'Unique saved item identifier';
COMMENT ON COLUMN bootcamp_shipp.saved_items.user_id IS 'Foreign key to users (who saved/accepted this match)';
COMMENT ON COLUMN bootcamp_shipp.saved_items.request_id IS 'Foreign key to requests table (nullable if just saving a listing)';
COMMENT ON COLUMN bootcamp_shipp.saved_items.listing_id IS 'Foreign key to listings table (nullable if just saving a request)';
COMMENT ON COLUMN bootcamp_shipp.saved_items.match_score IS 'Matching algorithm score (0.0 to 1.0) indicating quality of match';
COMMENT ON COLUMN bootcamp_shipp.saved_items.match_reason IS 'Human-readable reason for the match (category match, distance, priority alignment, etc.)';
COMMENT ON COLUMN bootcamp_shipp.saved_items.saved_at IS 'When the match was saved/accepted';
COMMENT ON COLUMN bootcamp_shipp.saved_items.status IS 'Lifecycle status of the saved match';
CREATE INDEX idx_saved_items_user ON bootcamp_shipp.saved_items(user_id);
CREATE INDEX idx_saved_items_request ON bootcamp_shipp.saved_items(request_id);
CREATE INDEX idx_saved_items_listing ON bootcamp_shipp.saved_items(listing_id);
CREATE INDEX idx_saved_items_status ON bootcamp_shipp.saved_items(status);
CREATE INDEX idx_saved_items_match_score ON bootcamp_shipp.saved_items(match_score DESC);
-- ============================================================================
-- 8. AGENT_ACTIVITY TABLE - Audit trail for AI/agent actions
-- ============================================================================
CREATE TABLE IF NOT EXISTS bootcamp_shipp.agent_activity (
    activity_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    tool_name VARCHAR(100) NOT NULL,
    entity_id VARCHAR(50),
    entity_type VARCHAR(50),
    action_status VARCHAR(50),
    input_params TEXT,
    output_result TEXT,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES bootcamp_shipp.users(user_id) ON DELETE CASCADE,
    CONSTRAINT chk_action_status CHECK(
        action_status IN ('SUCCESS', 'FAILURE', 'PENDING', 'ERROR')
    )
);
COMMENT ON TABLE bootcamp_shipp.agent_activity IS 'Audit log for AI/agent actions (matching, image analysis, route calculation, etc.)';
COMMENT ON COLUMN bootcamp_shipp.agent_activity.activity_id IS 'Unique activity/log record identifier';
COMMENT ON COLUMN bootcamp_shipp.agent_activity.user_id IS 'User who triggered the agent action (or system user if autonomous)';
COMMENT ON COLUMN bootcamp_shipp.agent_activity.tool_name IS 'Name of the tool invoked (e.g., image_analyzer, matcher, route_optimizer)';
COMMENT ON COLUMN bootcamp_shipp.agent_activity.entity_id IS 'ID of the entity being acted upon (listing_id, request_id, etc.)';
COMMENT ON COLUMN bootcamp_shipp.agent_activity.entity_type IS 'Type of entity (LISTING, REQUEST, SAVED_ITEM, USER)';
COMMENT ON COLUMN bootcamp_shipp.agent_activity.action_status IS 'Outcome of the action (SUCCESS, FAILURE, ERROR)';
COMMENT ON COLUMN bootcamp_shipp.agent_activity.input_params IS 'JSON-serialized input parameters to the tool';
COMMENT ON COLUMN bootcamp_shipp.agent_activity.output_result IS 'JSON-serialized result/output from the tool';
COMMENT ON COLUMN bootcamp_shipp.agent_activity.error_message IS 'Error details if action failed';
CREATE INDEX idx_agent_activity_user ON bootcamp_shipp.agent_activity(user_id);
CREATE INDEX idx_agent_activity_entity ON bootcamp_shipp.agent_activity(entity_id, entity_type);
CREATE INDEX idx_agent_activity_tool ON bootcamp_shipp.agent_activity(tool_name);
CREATE INDEX idx_agent_activity_status ON bootcamp_shipp.agent_activity(action_status);
CREATE INDEX idx_agent_activity_created ON bootcamp_shipp.agent_activity(created_at DESC);
-- ============================================================================
-- SEED DATA - Initial reference data
-- ============================================================================
INSERT INTO bootcamp_shipp.roles (role_id, role_name)
VALUES ('DONOR', 'DONOR'),
    ('REQUESTER', 'REQUESTER'),
    ('SHIPPING_PARTNER', 'SHIPPING_PARTNER') ON CONFLICT DO NOTHING;
-- ============================================================================
-- SCHEMA SUMMARY & DESIGN NOTES
-- ============================================================================
/*
 DESIGN PRINCIPLES:
 1. Normalization: 3NF with strategic denormalization for performance
 2. Referential Integrity: Foreign keys with appropriate cascade/restrict rules
 3. Audit Trail: created_at/updated_at on transactional tables; agent_activity for AI actions
 4. Soft Deletes: is_active flag on users for historical preservation
 5. Scalability: Indexes on foreign keys, status, and common query predicates
 6. Flexibility: JSON columns (input_params, output_result) for dynamic tool payloads
 7. Geography: Latitude/longitude coordinates for proximity-based matching (OpenRouteService)
 
 RELATIONSHIPS:
 - Users have many Roles (many-to-many via user_roles)
 - Users can be Donors (create Listings) or Requesters (create Requests)
 - Listings have many Files (one-to-many)
 - Requests and Listings are matched via Saved_Items (many-to-many pairing)
 - All actions logged in Agent_Activity for traceability and debugging
 
 CONSTRAINTS:
 - Role values are constrained to business roles
 - Listing and Request statuses are constrained to valid lifecycle states
 - Saved_Items must reference at least one of request_id or listing_id
 - Match scores are expected to be floats between 0.0 and 1.0
 
 INDEXES STRATEGY:
 - Foreign key columns indexed for JOIN performance
 - Status columns indexed for filtering (common query predicate)
 - Location columns (lat/lon) indexed for proximity queries
 - Activity timestamp indexed for audit log queries (DESC for latest first)
 - Match score indexed DESC for "best matches" queries
 
 SCHEMA-QUALIFICATION POLICY (Issue #1):
 All objects in this file are qualified with bootcamp_shipp.* — CREATE TABLE,
 COMMENT ON TABLE/COLUMN, CREATE INDEX, and FOREIGN KEY REFERENCES clauses.
 This script does not depend on search_path to resolve correctly. Any future
 migration file added to this repo must follow the same convention.
 */