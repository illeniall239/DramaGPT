# KB Standalone - AI-Powered Knowledge Base

A standalone knowledge base application with advanced RAG (Retrieval-Augmented Generation), SQL querying, predictive analytics, and automatic visualization generation. This is a single-user version extracted from EDI.ai, designed to work independently without authentication.

## Features

- **Document Processing**: Upload and process PDFs, DOCX, TXT files with automatic text extraction
- **Table Extraction**: Automatically extract and query tables from documents
- **Semantic Search**: Vector-based similarity search using pgvector and sentence-transformers
- **Advanced RAG**: Query expansion, cross-encoder reranking, MMR (Maximal Marginal Relevance) diversity
- **SQL Queries**: Query structured data (CSV/Excel) with natural language
- **Predictive Analytics**: Time series forecasting, regression, classification on your data
- **Auto Visualizations**: Automatic chart generation (matplotlib/plotly) from query results
- **Source Citations**: All answers include source references with relevance scores

## Tech Stack

### Backend
- **FastAPI**: High-performance Python web framework
- **Supabase + pgvector**: PostgreSQL with vector similarity search
- **sentence-transformers**: 384-dimensional embeddings (all-MiniLM-L6-v2)
- **LangChain**: LLM orchestration and document processing
- **Google Gemini 2.0 Flash**: LLM for query understanding and response generation
- **Prophet, XGBoost, scikit-learn**: Predictive analytics
- **matplotlib, plotly**: Visualization generation

### Frontend
- **Next.js 15**: React framework with App Router
- **TypeScript**: Type-safe development
- **Tailwind CSS**: Utility-first styling
- **Supabase Client**: Direct database queries for chat/document metadata

---

## Quick Start

### Prerequisites

- Python 3.9+
- Node.js 18+
- Supabase account (free tier works)
- Google API key for LLM

### 1. Database Setup

Create a new Supabase project and run the migration:

```bash
# Connect to your Supabase database
psql -h your-db.supabase.co -U postgres -d postgres

# Run migration
\i database/migration.sql

# Verify tables created
\dt
```

You should see 6 tables: `knowledge_bases`, `kb_documents`, `kb_document_chunks`, `kb_structured_data`, `kb_extracted_tables`, `chats`

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Supabase credentials and Google API key

# Start backend server
python main.py
```

Backend will run on `http://localhost:8000`

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Configure environment
cp .env.example .env
# Edit .env with backend URL and Supabase credentials

# Start development server
npm run dev
```

Frontend will run on `http://localhost:3000`

---

## Environment Configuration

### Backend `.env`

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
GOOGLE_API_KEY=your-google-api-key
PORT=8000
```

### Frontend `.env`

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

### Getting Supabase Credentials

1. Go to [supabase.com](https://supabase.com) and create a project
2. Navigate to Settings > API
3. Copy:
   - **Project URL** → `SUPABASE_URL`
   - **anon public** key → `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - **service_role** key → `SUPABASE_SERVICE_ROLE_KEY`

---

## Usage Guide

### 1. Create Knowledge Base

- Click "New KB" button in sidebar
- Enter name and optional description
- Click "Create"

### 2. Upload Documents

- Select a knowledge base
- Click upload icon (↑)
- Choose files: PDF, DOCX, TXT, CSV, XLSX
- Wait for processing to complete

**Supported Formats:**
- **Text Documents**: PDF, DOCX, TXT (chunked with embeddings for semantic search)
- **Structured Data**: CSV, Excel (loaded into SQLite for SQL queries)
- **Tables in Documents**: Automatically extracted from PDFs/DOCX

### 3. Create Chat and Ask Questions

- Click "+ New Chat" in the knowledge base
- Type your question in the chat interface
- Press Enter to send

**Example Questions:**
- "What are the main findings in the research paper?"
- "Show me sales data for Q4 2024"
- "Predict revenue for next 6 months"
- "Create a chart comparing product categories"

### 4. Review Answers

Answers include:
- **AI Response**: Generated answer based on retrieved context
- **Sources**: Relevant document chunks with similarity scores
- **Visualizations**: Auto-generated charts (if applicable)
- **SQL Results**: Query results from structured data (if applicable)

### 5. Predictive Analytics

For CSV/Excel files:
- Use natural language to request predictions
- Example: "Forecast sales for next quarter"
- Supported: time series, regression, classification, trend analysis

---

## API Endpoints

### Knowledge Base Management

- `POST /api/kb/create` - Create new knowledge base
- `GET /api/kb/list` - List all knowledge bases
- `DELETE /api/kb/{kb_id}` - Delete knowledge base

### File Operations

- `POST /api/kb/{kb_id}/upload` - Upload and process file

### Querying

- `POST /api/kb/{kb_id}/query` - Query knowledge base with RAG
  ```json
  {
    "question": "What is the main topic?",
    "chat_id": "optional-chat-id"
  }
  ```

- `POST /api/kb/{kb_id}/predict` - Run predictive analytics
  ```json
  {
    "target_column": "sales",
    "data_source_id": "uuid",
    "data_source_type": "structured",
    "prediction_type": "forecast",
    "periods": 10
  }
  ```

---

## Architecture

### Backend Flow

```
Upload File → DocumentProcessor → Embeddings → Supabase pgvector
                ↓ (tables)
           TableExtractor → SQLite DB → kb_extracted_tables

Query → RAG Engine → Vector Search (pgvector)
                  → SQL Query (if structured data)
                  → Predictive Analytics (if prediction requested)
                  → LLM Synthesis
                  → KBChartGenerator (if visualization needed)
```

### RAG Pipeline

1. **Query Embedding**: Generate 384-dim vector
2. **Query Expansion**: LLM generates semantic variations
3. **Multi-Query Retrieval**: Search with all variants
4. **Reranking**: Cross-encoder scoring for relevance
5. **MMR Diversity**: Select diverse, non-redundant results
6. **Context Building**: Combine document chunks + SQL results
7. **LLM Response**: Generate answer with citations

---

## Production Deployment

### Backend (Render/Railway)

```bash
# Push to GitHub
git init
git add .
git commit -m "Initial commit"
git push origin main

# On Render:
# 1. Connect GitHub repo
# 2. Set build command: pip install -r requirements.txt
# 3. Set start command: uvicorn main:app --host 0.0.0.0 --port $PORT
# 4. Add environment variables
```

### Frontend (Vercel)

```bash
# On Vercel:
# 1. Import GitHub repo
# 2. Framework preset: Next.js
# 3. Add environment variables
# 4. Deploy
```

### Database (Supabase)

Already hosted! Just ensure:
- pgvector extension enabled
- Migration script run
- RLS disabled (since single-user mode)

---

## Troubleshooting

### Backend won't start

- Check `SUPABASE_SERVICE_ROLE_KEY` is set (not anon key)
- Verify `GOOGLE_API_KEY` is valid
- Ensure port 8000 is not in use

### Frontend can't connect to backend

- Verify `NEXT_PUBLIC_API_URL` points to backend
- Check CORS settings in backend `main.py`
- Ensure backend is running

### File upload fails

- Check file size (default limit: 10MB)
- Verify Supabase service key has write permissions
- Check backend logs for processing errors

### Queries return no results

- Verify pgvector extension enabled: `CREATE EXTENSION IF NOT EXISTS vector;`
- Check embeddings were generated (query `kb_document_chunks` table)
- Ensure knowledge base has processed documents

### Visualizations not generating

- Check `static/visualizations/` directory exists
- Verify matplotlib/plotly installed
- Review backend logs for LLM chart code generation errors

---

## Differences from EDI

This standalone version has been simplified from the original EDI.ai application:

| Feature | EDI | KB Standalone |
|---------|-----|---------------|
| Authentication | Supabase Auth | None (single-user) |
| User Management | Multi-user with RLS | Single-user, no RLS |
| Workspaces | Separate feature | Removed |
| Database | RLS policies enforced | RLS disabled |
| API | user_id required | No user_id |

---

## Contributing

This is an extracted standalone version. For the full EDI.ai platform, see the main repository.

---

## License

MIT

---

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review backend logs: Check console output
3. Review frontend logs: Check browser console

---

## Credits

Extracted from [EDI.ai](https://github.com/your-repo/edi) - An AI-powered data analysis platform with knowledge base capabilities.
