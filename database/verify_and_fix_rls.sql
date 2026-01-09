-- Verify and Fix RLS for KB Standalone (Single-User Mode)
-- Run this in Supabase SQL Editor to ensure all tables are accessible

-- Disable RLS on all KB tables
ALTER TABLE knowledge_bases DISABLE ROW LEVEL SECURITY;
ALTER TABLE kb_documents DISABLE ROW LEVEL SECURITY;
ALTER TABLE kb_document_chunks DISABLE ROW LEVEL SECURITY;
ALTER TABLE kb_structured_data DISABLE ROW LEVEL SECURITY;
ALTER TABLE kb_extracted_tables DISABLE ROW LEVEL SECURITY;
ALTER TABLE chats DISABLE ROW LEVEL SECURITY;

-- Drop all existing RLS policies on these tables
DO $$
DECLARE
    pol RECORD;
BEGIN
    -- Drop policies for knowledge_bases
    FOR pol IN SELECT policyname FROM pg_policies WHERE tablename = 'knowledge_bases'
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON knowledge_bases', pol.policyname);
    END LOOP;

    -- Drop policies for kb_documents
    FOR pol IN SELECT policyname FROM pg_policies WHERE tablename = 'kb_documents'
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON kb_documents', pol.policyname);
    END LOOP;

    -- Drop policies for kb_document_chunks
    FOR pol IN SELECT policyname FROM pg_policies WHERE tablename = 'kb_document_chunks'
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON kb_document_chunks', pol.policyname);
    END LOOP;

    -- Drop policies for kb_structured_data
    FOR pol IN SELECT policyname FROM pg_policies WHERE tablename = 'kb_structured_data'
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON kb_structured_data', pol.policyname);
    END LOOP;

    -- Drop policies for kb_extracted_tables
    FOR pol IN SELECT policyname FROM pg_policies WHERE tablename = 'kb_extracted_tables'
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON kb_extracted_tables', pol.policyname);
    END LOOP;

    -- Drop policies for chats
    FOR pol IN SELECT policyname FROM pg_policies WHERE tablename = 'chats'
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON chats', pol.policyname);
    END LOOP;
END $$;

-- Verify RLS is disabled
SELECT
    tablename,
    rowsecurity as rls_enabled
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN ('knowledge_bases', 'kb_documents', 'kb_document_chunks',
                    'kb_structured_data', 'kb_extracted_tables', 'chats')
ORDER BY tablename;

-- Expected output: all tables should show rls_enabled = false
