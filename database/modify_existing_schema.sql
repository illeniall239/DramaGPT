-- KB Standalone - Modify Existing Schema
-- This script modifies existing EDI tables to work in single-user mode
-- WARNING: This will affect your main EDI application!

-- ============================================================================
-- Remove user_id column from knowledge_bases (if it exists)
-- ============================================================================
ALTER TABLE knowledge_bases
DROP COLUMN IF EXISTS user_id CASCADE;

-- Disable RLS on all KB tables
ALTER TABLE knowledge_bases DISABLE ROW LEVEL SECURITY;
ALTER TABLE kb_documents DISABLE ROW LEVEL SECURITY;
ALTER TABLE kb_document_chunks DISABLE ROW LEVEL SECURITY;
ALTER TABLE kb_structured_data DISABLE ROW LEVEL SECURITY;
ALTER TABLE kb_extracted_tables DISABLE ROW LEVEL SECURITY;
ALTER TABLE chats DISABLE ROW LEVEL SECURITY;

-- Drop all RLS policies
DROP POLICY IF EXISTS "Users can view own knowledge bases" ON knowledge_bases;
DROP POLICY IF EXISTS "Users can create own knowledge bases" ON knowledge_bases;
DROP POLICY IF EXISTS "Users can update own knowledge bases" ON knowledge_bases;
DROP POLICY IF EXISTS "Users can delete own knowledge bases" ON knowledge_bases;

DROP POLICY IF EXISTS "Users can view documents in their KBs" ON kb_documents;
DROP POLICY IF EXISTS "Users can create documents in their KBs" ON kb_documents;
DROP POLICY IF EXISTS "Users can update documents in their KBs" ON kb_documents;
DROP POLICY IF EXISTS "Users can delete documents in their KBs" ON kb_documents;

DROP POLICY IF EXISTS "Users can view chunks in their KBs" ON kb_document_chunks;
DROP POLICY IF EXISTS "Users can create chunks in their KBs" ON kb_document_chunks;
DROP POLICY IF EXISTS "Users can view structured data in their KBs" ON kb_structured_data;
DROP POLICY IF EXISTS "Users can create structured data in their KBs" ON kb_structured_data;
DROP POLICY IF EXISTS "Users can view extracted tables in their KBs" ON kb_extracted_tables;
DROP POLICY IF EXISTS "Users can create extracted tables in their KBs" ON kb_extracted_tables;

DROP POLICY IF EXISTS "Users can view own chats" ON chats;
DROP POLICY IF EXISTS "Users can create own chats" ON chats;
DROP POLICY IF EXISTS "Users can update own chats" ON chats;
DROP POLICY IF EXISTS "Users can delete own chats" ON chats;

-- Verify changes
SELECT 'Migration Complete!' as status;
SELECT 'Knowledge Bases Count: ' || COUNT(*) FROM knowledge_bases;
SELECT 'Documents Count: ' || COUNT(*) FROM kb_documents;
SELECT 'Chats Count: ' || COUNT(*) FROM chats;
