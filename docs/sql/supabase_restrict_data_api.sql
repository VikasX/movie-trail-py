-- MANUAL OPERATOR SCRIPT: review before running in Supabase SQL Editor.
-- This file was prepared during the security audit; it has NOT been executed.
-- Only Django-owned table/sequence grants are changed. No rows are deleted.
-- Django uses direct PostgreSQL access, not the anon/authenticated/service_role API roles.
-- First disable the Data API if no other application needs it, and disable automatic exposure.
-- Confirm no other application relies on Data API access to these exact Django tables.
BEGIN;
DO $audit$
DECLARE
    item record;
    sequence_name text;
BEGIN
    FOR item IN
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public' AND tablename IN (
        'account_emailaddress',
        'account_emailconfirmation',
        'accounts_accounttoken',
        'accounts_userpreferences',
        'auth_group',
        'auth_group_permissions',
        'auth_permission',
        'auth_user',
        'auth_user_groups',
        'auth_user_user_permissions',
        'catalog_cachelease',
        'catalog_ratelimitbucket',
        'catalog_titlesnapshot',
        'cinescope_cache',
        'core_samplerecord',
        'django_admin_log',
        'django_content_type',
        'django_migrations',
        'django_session',
        'library_collection',
        'library_collectionmembership',
        'library_guestcollectionmapping',
        'library_publicshare',
        'library_recenttitle',
        'library_savedtitle',
        'library_syncreceipt',
        'socialaccount_socialaccount',
        'socialaccount_socialapp',
        'socialaccount_socialtoken'
        )
    LOOP
        EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE %I.%I FROM PUBLIC, anon, authenticated, service_role',
                       'public', item.tablename);
        -- Also close sequence access for the affected table's serial/identity columns.
        FOR sequence_name IN
            SELECT pg_get_serial_sequence(format('%I.%I', 'public', item.tablename), attname)
            FROM pg_attribute
            WHERE attrelid = format('%I.%I', 'public', item.tablename)::regclass
              AND attnum > 0 AND NOT attisdropped
        LOOP
            IF sequence_name IS NOT NULL THEN
                EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE %s FROM PUBLIC, anon, authenticated, service_role',
                               sequence_name);
            END IF;
        END LOOP;
    END LOOP;
END;
$audit$;
-- Future objects: this applies to the migration role, NOT all roles globally.
-- postgres is the current migration owner. Repeat for a dedicated migration role if adopted.
-- These defaults affect future objects created by that role throughout public: review shared-project needs.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE ALL PRIVILEGES ON TABLES FROM PUBLIC, anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE ALL PRIVILEGES ON SEQUENCES FROM PUBLIC, anon, authenticated, service_role;
COMMIT;

-- Verification: expect NO rows. These are effective privileges, including inherited grants.
-- This checks all audited Django table prefixes plus the database cache.
SELECT t.tablename, r.rolname
FROM pg_tables t
CROSS JOIN pg_roles r
WHERE t.schemaname = 'public'
  AND (t.tablename ~ '^(auth_|django_|account_|accounts_|socialaccount_|catalog_|library_|core_)'
       OR t.tablename = 'cinescope_cache')
  AND r.rolname IN ('anon', 'authenticated', 'service_role')
  AND has_table_privilege(r.rolname, format('%I.%I', t.schemaname, t.tablename),
                          'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER');
