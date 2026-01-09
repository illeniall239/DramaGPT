-- KB Standalone Database Migration
-- Single-user knowledge base schema without RLS or user_id columns
-- Run this on a fresh Supabase project

-- Enable pgvector extension for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- Table 1: knowledge_bases
-- Stores knowledge base metadata (no user_id in single-user mode)
-- ============================================================================
CREATE TABLE knowledge_bases (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()),
    embedding_model TEXT DEFAULT 'sentence-transformers/all-MiniLM-L6-v2',
    chunk_size INTEGER DEFAULT 1000,
    chunk_overlap INTEGER DEFAULT 200
);

CREATE INDEX idx_kb_updated_at ON knowledge_bases(updated_at DESC);

-- Disable RLS for single-user mode
ALTER TABLE knowledge_bases DISABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Table 2: kb_documents
-- Stores uploaded document metadata
-- ============================================================================
CREATE TABLE kb_documents (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    kb_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK (file_type IN ('pdf', 'docx', 'txt', 'csv', 'xlsx')),
    file_size_bytes BIGINT,
    upload_date TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()),
    processing_status TEXT DEFAULT 'pending' CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed')),
    error_message TEXT,
    page_count INTEGER,
    total_chunks INTEGER,
    has_tables BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_kb_docs_kb_id ON kb_documents(kb_id);
CREATE INDEX idx_kb_docs_status ON kb_documents(processing_status);

ALTER TABLE kb_documents DISABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Table 3: kb_document_chunks
-- Stores text chunks with vector embeddings for semantic search
-- ============================================================================
CREATE TABLE kb_document_chunks (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
    kb_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(384),  -- 384-dimensional embeddings from sentence-transformers
    chunk_metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW())
);

CREATE INDEX idx_kb_chunks_doc_id ON kb_document_chunks(document_id);
CREATE INDEX idx_kb_chunks_kb_id ON kb_document_chunks(kb_id);

-- IVFFlat index for fast approximate nearest neighbor search
CREATE INDEX idx_kb_chunks_embedding ON kb_document_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

ALTER TABLE kb_document_chunks DISABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Table 4: kb_structured_data
-- Stores metadata for uploaded CSV/Excel files
-- ============================================================================
CREATE TABLE kb_structured_data (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    kb_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK (file_type IN ('csv', 'xlsx')),
    upload_date TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()),
    row_count INTEGER,
    column_count INTEGER,
    column_names TEXT[],
    data_preview JSONB,  -- First 5 rows as JSON
    temp_db_path TEXT,   -- Path to SQLite database on filesystem
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX idx_kb_struct_kb_id ON kb_structured_data(kb_id);

ALTER TABLE kb_structured_data DISABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Table 5: kb_extracted_tables
-- Stores tables extracted from documents (PDF/DOCX)
-- ============================================================================
CREATE TABLE kb_extracted_tables (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
    kb_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    page_number INTEGER,
    table_index INTEGER,
    table_data JSONB NOT NULL,
    column_names TEXT[],
    row_count INTEGER,
    temp_db_path TEXT,   -- Path to SQLite database for table data
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW())
);

CREATE INDEX idx_kb_extracted_kb_id ON kb_extracted_tables(kb_id);
CREATE INDEX idx_kb_extracted_doc_id ON kb_extracted_tables(document_id);

ALTER TABLE kb_extracted_tables DISABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Table 6: chats
-- Stores chat threads for knowledge bases (no workspace_id, no user_id)
-- ============================================================================
CREATE TABLE chats (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    kb_id UUID NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    title TEXT DEFAULT 'New Chat',
    messages JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW()),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT TIMEZONE('utc', NOW())
);

CREATE INDEX idx_chats_kb_id ON chats(kb_id);
CREATE INDEX idx_chats_updated_at ON chats(updated_at DESC);

ALTER TABLE chats DISABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Functions
-- ============================================================================

-- Vector similarity search function (cosine similarity)
CREATE OR REPLACE FUNCTION match_kb_documents(
  query_embedding vector(384),
  kb_id_param uuid,
  match_count int DEFAULT 5
)
RETURNS TABLE (
  id uuid,
  document_id uuid,
  content text,
  chunk_metadata jsonb,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    kb_document_chunks.id,
    kb_document_chunks.document_id,
    kb_document_chunks.content,
    kb_document_chunks.chunk_metadata,
    1 - (kb_document_chunks.embedding <=> query_embedding) AS similarity
  FROM kb_document_chunks
  WHERE kb_document_chunks.kb_id = kb_id_param
  ORDER BY kb_document_chunks.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Auto-update trigger for updated_at columns
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = TIMEZONE('utc', NOW());
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to knowledge_bases
CREATE TRIGGER update_kb_updated_at
    BEFORE UPDATE ON knowledge_bases
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Apply trigger to chats
CREATE TRIGGER update_chats_updated_at
    BEFORE UPDATE ON chats
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Verification Queries
-- ============================================================================

-- Run these to verify the migration was successful:
-- SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
-- SELECT * FROM pg_extension WHERE extname = 'vector';
-- \d knowledge_bases
-- \d kb_document_chunks
