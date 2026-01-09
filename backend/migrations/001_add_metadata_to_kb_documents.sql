-- Migration: Add metadata column to kb_documents for unified approach
-- This allows storing structured data metadata in the same table as unstructured documents

-- Add metadata column if it doesn't exist
ALTER TABLE kb_documents
  ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';

-- Add index on metadata for faster queries
CREATE INDEX IF NOT EXISTS idx_kb_documents_metadata
  ON kb_documents USING GIN (metadata);

-- Add comment explaining the column
COMMENT ON COLUMN kb_documents.metadata IS
  'Stores file-specific metadata. For structured data (Excel/CSV): row_count, column_count, column_names, data_preview. For all files: processed_with, file_size, etc.';
