"""
KB Standalone - Main FastAPI Server
Simplified knowledge base backend without authentication (single-user mode)
"""

import os
import logging
from typing import Dict, Any
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Import settings for LLM configuration
try:
    from settings import LLM as settings_llm
    settings = type('Settings', (), {'LLM': settings_llm})()
except ImportError:
    # Fallback if settings.py not available - use Groq LLaMA 3.3 70B (128k context)
    from langchain_groq import ChatGroq

    groq_api_key = os.getenv('NEXT_PUBLIC_GROQ_API_KEY')
    if not groq_api_key:
        raise ValueError("NEXT_PUBLIC_GROQ_API_KEY not found in environment variables. Please check your .env file.")

    settings = type('Settings', (), {
        'LLM': ChatGroq(
            model="",  # 128k context window!
            temperature=0.0,  # ✅ Deterministic responses
            groq_api_key=groq_api_key,
            max_tokens=8000,
            model_kwargs={'seed': 42}  # ✅ Fixed seed for reproducibility
        )
    })()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="KB Standalone API", version="1.0.0")

# CORS configuration - allow all origins in single-user mode
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for visualizations
app.mount("/static", StaticFiles(directory="static"), name="static")

logger.info("✅ KB Standalone API initialized")


# ============================================================================
# HEALTH CHECK ENDPOINT
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring and deployment platforms."""
    return {"status": "healthy", "service": "KB Standalone API"}


# ============================================================================
# KNOWLEDGE BASE ENDPOINTS
# ============================================================================

@app.post("/api/kb/create")
async def create_knowledge_base(request: Dict[str, Any]):
    """
    Create a new knowledge base (single-user mode - no user_id required).

    Body: {
        "name": str,
        "description": str (optional)
    }
    """
    try:
        from document_processor import get_supabase_client

        supabase = get_supabase_client()
        name = request.get('name')
        description = request.get('description', '')

        if not name:
            raise HTTPException(status_code=400, detail="name is required")

        # Insert into knowledge_bases table (no user_id in single-user mode)
        result = supabase.table('knowledge_bases').insert({
            'name': name,
            'description': description
        }).execute()

        if result.data and len(result.data) > 0:
            kb_id = result.data[0]['id']
            logger.info(f"✅ Created knowledge base: {kb_id} - {name}")
            return {"success": True, "kb_id": kb_id, "kb": result.data[0]}
        else:
            raise HTTPException(status_code=500, detail="Failed to create knowledge base")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error creating knowledge base: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/kb/list")
async def list_knowledge_bases():
    """List all knowledge bases (single-user mode - no user filtering)."""
    try:
        from document_processor import get_supabase_client

        supabase = get_supabase_client()
        result = supabase.table('knowledge_bases').select('*').order('updated_at', desc=True).execute()

        logger.info(f"📚 Listed {len(result.data or [])} knowledge bases")
        return {"knowledge_bases": result.data or []}

    except Exception as e:
        logger.error(f"❌ Error listing knowledge bases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/kb/{kb_id}")
async def delete_knowledge_base(kb_id: str):
    """Delete a knowledge base and all associated data (cascade delete)."""
    try:
        from document_processor import get_supabase_client

        supabase = get_supabase_client()

        # Cascade delete will handle related tables automatically
        result = supabase.table('knowledge_bases').delete().eq('id', kb_id).execute()

        logger.info(f"🗑️ Deleted knowledge base: {kb_id}")
        return {"success": True, "message": "Knowledge base deleted successfully"}

    except Exception as e:
        logger.error(f"❌ Error deleting knowledge base: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/kb/{kb_id}/documents/{document_id}")
async def delete_kb_document(kb_id: str, document_id: str):
    """
    Delete a document from the knowledge base.

    Deletes the document from kb_documents and drops the Postgres table.
    """
    try:
        from document_processor import get_supabase_client
        from sqlalchemy import create_engine, text

        supabase = get_supabase_client()

        # Get document from kb_documents
        doc_result = supabase.table('kb_documents') \
            .select('*') \
            .eq('id', document_id) \
            .eq('kb_id', kb_id) \
            .execute()

        if not doc_result.data or len(doc_result.data) == 0:
            raise HTTPException(status_code=404, detail="Document not found in this knowledge base")

        doc = doc_result.data[0]
        metadata = doc.get('metadata', {})
        postgres_table = metadata.get('postgres_table') or metadata.get('table_name')

        # Delete the Postgres table if it exists
        if postgres_table:
            db_url = os.getenv('SUPABASE_DB_URL')
            if db_url:
                try:
                    engine = create_engine(db_url)
                    with engine.connect() as conn:
                        conn.execute(text(f'DROP TABLE IF EXISTS "{postgres_table}"'))
                        conn.commit()
                    logger.info(f"🗑️ Dropped Postgres table: {postgres_table}")
                except Exception as e:
                    logger.warning(f"Failed to drop Postgres table {postgres_table}: {e}")

        # Delete document record from kb_documents
        supabase.table('kb_documents').delete().eq('id', document_id).execute()

        logger.info(f"🗑️ Deleted document: {document_id} from KB: {kb_id}")
        return {"success": True, "message": "Document deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error deleting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/kb/{kb_id}/documents")
async def list_kb_documents(kb_id: str):
    """
    List all documents in a knowledge base with metadata.

    Returns:
    {
        "documents": [
            {
                "id": str,
                "kb_id": str,
                "filename": str,
                "file_type": str,
                "file_size_bytes": int,
                "upload_date": str,
                "processing_status": str,
                "error_message": str | null,
                "page_count": int | null,
                "total_chunks": int | null,
                "has_tables": bool,
                "metadata": dict
            }
        ],
        "count": int
    }
    """
    try:
        from document_processor import get_supabase_client

        supabase = get_supabase_client()

        # Verify KB exists
        kb_result = supabase.table('knowledge_bases').select('id').eq('id', kb_id).single().execute()
        if not kb_result.data:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        # Get documents from primary table
        docs_result = supabase.table('kb_documents') \
            .select('*') \
            .eq('kb_id', kb_id) \
            .order('upload_date', desc=True) \
            .execute()

        documents = docs_result.data or []

        # Fallback: include structured-data entries that may not have a kb_documents row
        structured_result = supabase.table('kb_structured_data') \
            .select('*') \
            .eq('kb_id', kb_id) \
            .order('upload_date', desc=True) \
            .execute()

        structured_docs = []
        if structured_result.data:
            existing_ids = {doc.get('id') for doc in documents}
            existing_filenames = {doc.get('filename') for doc in documents}
            for row in structured_result.data:
                # Skip if a matching doc already exists (by filename or id)
                if row.get('id') in existing_ids or row.get('filename') in existing_filenames:
                    continue
                structured_docs.append({
                    "id": row.get("id"),
                    "kb_id": row.get("kb_id"),
                    "filename": row.get("filename"),
                    "file_type": row.get("file_type"),
                    "file_size_bytes": None,
                    "upload_date": row.get("upload_date"),
                    "processing_status": "completed",
                    "error_message": None,
                    "page_count": 1,
                    "total_chunks": row.get("row_count"),
                    "has_tables": False,
                    "metadata": {
                        "row_count": row.get("row_count"),
                        "column_count": row.get("column_count"),
                        "column_names": row.get("column_names"),
                        "data_preview": row.get("data_preview"),
                    }
                })

        merged_documents = structured_docs + documents
        logger.info(f"📄 Listed {len(merged_documents)} documents for KB {kb_id} (docs={len(documents)}, structured={len(structured_docs)})")

        return {
            "documents": merged_documents,
            "count": len(merged_documents)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error listing documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/kb/{kb_id}/upload")
async def upload_to_kb(kb_id: str, file: UploadFile = File(...)):
    """
    Upload and process file to knowledge base.

    Supports: PDF, DOCX, TXT, CSV, Excel

    Flow:
    1. Detect file type
    2. Save temporarily
    3. Process based on type:
       - PDF/DOCX/TXT -> DocumentProcessor -> embeddings -> pgvector
       - CSV/Excel -> DataHandler -> temp SQLite DB
    4. Update database with metadata
    5. Delete temp file
    """
    import shutil
    from document_processor import get_supabase_client

    logger.info(f"📁 Uploading file to KB {kb_id}: {file.filename}")

    try:
        # Get file extension
        file_ext = file.filename.split('.')[-1].lower() if '.' in file.filename else ''

        # Save temporary file
        temp_filename = f"temp_{kb_id}_{file.filename}"
        temp_path = temp_filename

        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size = os.path.getsize(temp_path)
        logger.info(f"Saved temp file: {temp_path} ({file_size} bytes)")

        supabase = get_supabase_client()

        # Route to appropriate processor
        if file_ext == 'pdf':
            await process_pdf_for_kb(kb_id, temp_path, file.filename, supabase)
        elif file_ext == 'docx':
            await process_docx_for_kb(kb_id, temp_path, file.filename, supabase)
        elif file_ext == 'txt':
            await process_txt_for_kb(kb_id, temp_path, file.filename, supabase)
        elif file_ext in ['csv', 'xlsx']:
            await process_structured_for_kb(kb_id, temp_path, file.filename, supabase)
        else:
            os.remove(temp_path)
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {file_ext}")

        # Delete temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
            logger.info(f"Deleted temp file: {temp_path}")

        return {
            "success": True,
            "message": f"File {file.filename} uploaded and processed successfully",
            "file_type": file_ext
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error uploading file: {e}")
        # Clean up temp file on error
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/kb/{kb_id}/query")
async def query_knowledge_base(kb_id: str, request: Dict[str, Any]):
    """
    Query knowledge base with RAG + SQL + Predictions.

    Body: {
        "question": str,
        "chat_id": str (optional)
    }
    """
    try:
        from kb_rag_engine import get_kb_rag_engine
        from document_processor import get_supabase_client
        from kb_chart_helper import generate_chart_from_sql_results

        question = request.get('question')
        chat_id = request.get('chat_id')

        if not question:
            raise HTTPException(status_code=400, detail="question is required")

        logger.info(f"🔍 KB Query - KB: {kb_id}, Chat: {chat_id}")
        logger.info(f"Question: {question}")

        # Initialize RAG engine
        supabase = get_supabase_client()
        rag_engine = get_kb_rag_engine(settings.LLM, supabase)

        # Load conversation history from database
        conversation_history = []
        if chat_id:
            try:
                chat_result = supabase.table('chats').select('messages').eq('id', chat_id).single().execute()
                if chat_result.data:
                    # Get last 10 messages (5 exchanges)
                    all_messages = chat_result.data.get('messages', [])
                    conversation_history = all_messages[-10:] if len(all_messages) > 10 else all_messages
                    logger.info(f"📜 Loaded {len(conversation_history)} messages from conversation history")
            except Exception as e:
                logger.warning(f"Failed to load conversation history: {e}")

        # Query KB with conversation history
        result = rag_engine.query_kb(kb_id, question, top_k=5, conversation_history=conversation_history)

        # Generate visualization if needed
        if result.get('visualization_needed', {}).get('should_visualize'):
            viz_info = result['visualization_needed']
            logger.info(f"📊 Generating visualization: {viz_info.get('suggested_chart')}")

            try:
                visualization = generate_chart_from_sql_results(
                    query=viz_info['query'],
                    sql_results=viz_info['sql_data'],
                    kb_id=kb_id,
                    llm=settings.LLM,
                    suggested_chart=viz_info.get('suggested_chart', 'auto')
                )

                if visualization:
                    logger.info(f"✅ Generated {visualization['type']}: {visualization['filename']}")
                    result['visualization'] = {
                        "type": visualization["type"],
                        "path": f"/static/visualizations/{visualization['filename']}"
                    }
            except Exception as viz_error:
                logger.error(f"❌ Visualization generation failed: {viz_error}")

            # Remove internal metadata
            result.pop('visualization_needed', None)

        # Save to chat history if chat_id provided
        if chat_id and 'response' in result:
            try:
                # Get current messages
                chat_result = supabase.table('chats').select('messages').eq('id', chat_id).single().execute()
                messages = chat_result.data.get('messages', []) if chat_result.data else []

                # Add user message and AI response
                messages.append({
                    'role': 'user',
                    'content': question,
                    'timestamp': pd.Timestamp.now().isoformat()
                })

                assistant_message = {
                    'role': 'assistant',
                    'content': result['response'],
                    'timestamp': pd.Timestamp.now().isoformat(),
                    'sources': result.get('sources', [])
                }

                # Include visualization if generated
                if 'visualization' in result:
                    assistant_message['visualization'] = result['visualization']

                messages.append(assistant_message)

                # Update chat
                supabase.table('chats').update({
                    'messages': messages,
                    'updated_at': pd.Timestamp.now().isoformat()
                }).eq('id', chat_id).execute()

            except Exception as e:
                logger.warning(f"Failed to save to chat history: {e}")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error querying KB: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/kb/{kb_id}/predict")
async def predict_kb_data(kb_id: str, request: Dict[str, Any]):
    """
    Run predictive analytics on KB data (structured or extracted tables).

    Body: {
        "target_column": str,
        "data_source_id": str,
        "data_source_type": "structured" | "extracted_table",
        "prediction_type": str (optional),
        "periods": int (optional)
    }
    """
    try:
        from document_processor import get_supabase_client
        from predictive_analysis import PredictiveAnalyzer
        from sqlalchemy import create_engine

        target_column = request.get('target_column')
        data_source_id = request.get('data_source_id')
        data_source_type = request.get('data_source_type')
        prediction_type = request.get('prediction_type', 'auto')
        periods = request.get('periods', 10)

        if not all([target_column, data_source_id, data_source_type]):
            raise HTTPException(status_code=400, detail="Missing required parameters")

        logger.info(f"📈 KB Prediction - KB: {kb_id}, Source: {data_source_type}")

        supabase = get_supabase_client()

        # Load data based on source type
        if data_source_type == 'structured':
            result = supabase.table('kb_structured_data').select('*').eq('id', data_source_id).single().execute()
            if not result.data:
                raise HTTPException(status_code=404, detail="Structured data not found")
            temp_db_path = result.data['temp_db_path']

        elif data_source_type == 'extracted_table':
            result = supabase.table('kb_extracted_tables').select('*').eq('id', data_source_id).single().execute()
            if not result.data:
                raise HTTPException(status_code=404, detail="Extracted table not found")
            temp_db_path = result.data['temp_db_path']
        else:
            raise HTTPException(status_code=400, detail="Invalid data_source_type")

        # Load data from SQLite
        engine = create_engine(f'sqlite:///{temp_db_path}')
        df = pd.read_sql_table('data_table', engine)

        # Run prediction
        analyzer = PredictiveAnalyzer(df, llm_client=settings.LLM)
        prediction_result = analyzer.auto_predict(target_column, prediction_type, periods)

        return prediction_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error in KB prediction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate-title")
async def generate_chat_title(request: Request):
    """
    Generate a concise, meaningful title (3-5 words) from user's first message.
    """
    try:
        data = await request.json()
        user_message = data.get('message', '')

        if not user_message:
            return JSONResponse({'title': 'New Chat'}, status_code=200)

        # Use LLM to generate concise title
        llm = settings.LLM

        prompt = f"""Generate a very concise, meaningful title (3-5 words maximum) for this chat conversation based on the user's first message.

User's message: "{user_message}"

Requirements:
- 3-5 words only
- Capitalize first letter of each word
- Be descriptive and specific
- No quotes or special formatting
- Just return the title, nothing else

Title:"""

        response = llm.invoke(prompt)
        title = response.content.strip()

        # Ensure title is reasonable length
        if len(title) > 60:
            title = title[:57] + '...'

        # Fallback if LLM fails
        if not title or title.lower() == 'new chat':
            title = user_message[:40].strip() + ('...' if len(user_message) > 40 else '')

        logger.info(f"✅ Generated chat title: {title}")
        return JSONResponse({'title': title}, status_code=200)

    except Exception as e:
        logger.error(f"❌ Error generating chat title: {str(e)}")
        # Return fallback title on error
        return JSONResponse({'title': 'New Chat'}, status_code=200)


# ============================================================================
# HELPER FUNCTIONS FOR FILE PROCESSING
# ============================================================================

async def process_pdf_for_kb(kb_id: str, file_path: str, filename: str, supabase):
    """Process PDF: extract text, tables, generate embeddings."""
    from document_processor import DocumentProcessor, TableExtractor

    logger.info(f"📄 Processing PDF for KB: {filename}")

    try:
        # Create document record
        doc_result = supabase.table('kb_documents').insert({
            'kb_id': kb_id,
            'filename': filename,
            'file_type': 'pdf',
            'file_size_bytes': os.path.getsize(file_path),
            'processing_status': 'processing'
        }).execute()

        if not doc_result.data or len(doc_result.data) == 0:
            raise Exception("Failed to create document record")

        doc_id = doc_result.data[0]['id']
        logger.info(f"Created document record: {doc_id}")

        # Process PDF
        processor = DocumentProcessor()
        result = processor.process_pdf(file_path, kb_id, doc_id)

        # Generate embeddings
        if result['text_chunks']:
            embeddings = processor.generate_embeddings(result['text_chunks'])
            metadata = [{'page': i // 10 + 1} for i in range(len(result['text_chunks']))]
            processor.save_to_vector_db(kb_id, doc_id, result['text_chunks'],
                                       embeddings, metadata, supabase)

        # Process extracted tables
        if result['tables']:
            table_extractor = TableExtractor()

            for table_data in result['tables']:
                try:
                    df = pd.DataFrame(table_data['data'])
                    temp_db_path = table_extractor.create_temp_db_for_table(
                        df, kb_id, f"{doc_id}_table_{table_data['table_index']}"
                    )

                    supabase.table('kb_extracted_tables').insert({
                        'document_id': doc_id,
                        'kb_id': kb_id,
                        'page_number': table_data['page'],
                        'table_index': table_data['table_index'],
                        'table_data': table_data['data'],
                        'column_names': table_data['columns'],
                        'row_count': table_data['row_count'],
                        'temp_db_path': temp_db_path
                    }).execute()

                    logger.info(f"Saved table {table_data['table_index']} from page {table_data['page']}")
                except Exception as e:
                    logger.warning(f"Failed to process table {table_data['table_index']}: {e}")

        # Update document status to completed
        supabase.table('kb_documents').update({
            'processing_status': 'completed',
            'page_count': result['page_count'],
            'total_chunks': len(result['text_chunks']),
            'has_tables': result['has_tables']
        }).eq('id', doc_id).execute()

        logger.info(f"✅ PDF processing complete: {filename}")

    except Exception as e:
        logger.error(f"❌ Error processing PDF: {e}")
        # Mark as failed
        try:
            supabase.table('kb_documents').update({
                'processing_status': 'failed',
                'error_message': str(e)
            }).eq('id', doc_id).execute()
        except:
            pass
        raise


async def process_docx_for_kb(kb_id: str, file_path: str, filename: str, supabase):
    """Process DOCX: extract text, tables, generate embeddings."""
    from document_processor import DocumentProcessor, TableExtractor

    logger.info(f"📝 Processing DOCX for KB: {filename}")

    try:
        # Create document record
        doc_result = supabase.table('kb_documents').insert({
            'kb_id': kb_id,
            'filename': filename,
            'file_type': 'docx',
            'file_size_bytes': os.path.getsize(file_path),
            'processing_status': 'processing'
        }).execute()

        if not doc_result.data or len(doc_result.data) == 0:
            raise Exception("Failed to create document record")

        doc_id = doc_result.data[0]['id']
        logger.info(f"Created document record: {doc_id}")

        # Process DOCX
        processor = DocumentProcessor()
        result = processor.process_docx(file_path, kb_id, doc_id)

        # Generate embeddings
        if result['text_chunks']:
            embeddings = processor.generate_embeddings(result['text_chunks'])
            metadata = [{'section': i // 10 + 1} for i in range(len(result['text_chunks']))]
            processor.save_to_vector_db(kb_id, doc_id, result['text_chunks'],
                                       embeddings, metadata, supabase)

        # Process extracted tables if any
        if result.get('tables'):
            table_extractor = TableExtractor()

            for table_data in result['tables']:
                try:
                    df = pd.DataFrame(table_data['data'])
                    temp_db_path = table_extractor.create_temp_db_for_table(
                        df, kb_id, f"{doc_id}_table_{table_data['table_index']}"
                    )

                    supabase.table('kb_extracted_tables').insert({
                        'document_id': doc_id,
                        'kb_id': kb_id,
                        'page_number': 1,
                        'table_index': table_data['table_index'],
                        'table_data': table_data['data'],
                        'column_names': table_data['columns'],
                        'row_count': table_data['row_count'],
                        'temp_db_path': temp_db_path
                    }).execute()

                    logger.info(f"Saved table {table_data['table_index']} from DOCX")
                except Exception as e:
                    logger.warning(f"Failed to process table {table_data['table_index']}: {e}")

        # Update document status to completed
        supabase.table('kb_documents').update({
            'processing_status': 'completed',
            'page_count': 1,
            'total_chunks': len(result['text_chunks']),
            'has_tables': result.get('has_tables', False)
        }).eq('id', doc_id).execute()

        logger.info(f"✅ DOCX processing complete: {filename}")

    except Exception as e:
        logger.error(f"❌ Error processing DOCX: {e}")
        # Mark as failed
        try:
            supabase.table('kb_documents').update({
                'processing_status': 'failed',
                'error_message': str(e)
            }).eq('id', doc_id).execute()
        except:
            pass
        raise


async def process_txt_for_kb(kb_id: str, file_path: str, filename: str, supabase):
    """Process TXT: extract text, generate embeddings."""
    from document_processor import DocumentProcessor

    logger.info(f"📃 Processing TXT for KB: {filename}")

    try:
        # Create document record
        doc_result = supabase.table('kb_documents').insert({
            'kb_id': kb_id,
            'filename': filename,
            'file_type': 'txt',
            'file_size_bytes': os.path.getsize(file_path),
            'processing_status': 'processing'
        }).execute()

        if not doc_result.data or len(doc_result.data) == 0:
            raise Exception("Failed to create document record")

        doc_id = doc_result.data[0]['id']
        logger.info(f"Created document record: {doc_id}")

        # Process TXT
        processor = DocumentProcessor()
        result = processor.process_txt(file_path, kb_id, doc_id)

        # Generate embeddings
        if result['text_chunks']:
            embeddings = processor.generate_embeddings(result['text_chunks'])
            metadata = [{'chunk_index': i} for i in range(len(result['text_chunks']))]
            processor.save_to_vector_db(kb_id, doc_id, result['text_chunks'],
                                       embeddings, metadata, supabase)

        # Update document status to completed
        supabase.table('kb_documents').update({
            'processing_status': 'completed',
            'page_count': 1,
            'total_chunks': len(result['text_chunks']),
            'has_tables': False
        }).eq('id', doc_id).execute()

        logger.info(f"✅ TXT processing complete: {filename}")

    except Exception as e:
        logger.error(f"❌ Error processing TXT: {e}")
        # Mark as failed
        try:
            supabase.table('kb_documents').update({
                'processing_status': 'failed',
                'error_message': str(e)
            }).eq('id', doc_id).execute()
        except:
            pass
        raise


async def process_structured_for_kb(kb_id: str, file_path: str, filename: str, supabase):
    """
    Process CSV/Excel using SQL agent approach.

    Implementation:
    1. Load file with pandas
    2. Create Postgres table with the data
    3. Store metadata in kb_documents
    4. SQL agent queries the Postgres table directly
    """
    import pandas as pd
    import json

    logger.info(f"📊 Processing structured data for SQL agent: {filename}")

    try:
        # Load the file with pandas
        file_ext = filename.split('.')[-1].lower()
        if file_ext == 'csv':
            df = pd.read_csv(file_path)
        elif file_ext == 'xlsx':
            df = pd.read_excel(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_ext}")

        logger.info(f"📊 Loaded {len(df)} rows, {len(df.columns)} columns from {filename}")

        # Convert DataFrame preview to JSON-safe format
        preview_df = df.head(5).copy()
        data_preview = json.loads(preview_df.to_json(orient='records', date_format='iso'))

        # LOAD DATA INTO POSTGRES (production-ready persistence)
        import re
        from sqlalchemy import create_engine

        # Get Postgres connection from environment
        db_url = os.getenv('SUPABASE_DB_URL')
        if not db_url:
            raise ValueError("SUPABASE_DB_URL not found in environment variables")

        # Create unique table name for this KB's data (lowercase for Postgres compatibility)
        safe_filename = re.sub(r'[^a-zA-Z0-9]', '_', filename)
        table_name = f'kb_data_{kb_id[:8]}_{safe_filename}'.lower()

        # Connect to Postgres and load data
        engine = create_engine(db_url)
        df.to_sql(table_name, engine, index=False, if_exists='replace')

        logger.info(f"📊 Loaded data into Postgres table: {table_name}")

        # Build metadata for structured data
        file_metadata = {
            'type': 'structured',
            'row_count': len(df),
            'column_count': len(df.columns),
            'column_names': df.columns.tolist(),
            'data_preview': data_preview,
            'processed_with': 'sql_agent_postgres',
            # SQL agent info (Postgres)
            'postgres_table': table_name,
            'table_name': table_name  # For backwards compatibility
        }

        # Store in kb_documents with metadata
        doc_insert = supabase.table('kb_documents').insert({
            'kb_id': kb_id,
            'filename': filename,
            'file_type': file_ext,
            'metadata': file_metadata
        }).execute()

        doc_id = doc_insert.data[0]['id']
        logger.info(f"✅ Processed {filename}: {len(df)} rows → Postgres table '{table_name}'")

    except Exception as e:
        logger.error(f"❌ Error processing structured data: {e}")
        raise


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    # Suppress watchfiles DEBUG logging
    logging.getLogger("watchfiles").setLevel(logging.WARNING)

    port = int(os.environ.get("PORT", 8000))
    logger.info(f"🚀 Starting KB Standalone API on port {port}")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        reload_excludes=["*.log", "*.db"]
    )
