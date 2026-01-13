"""
Knowledge Base RAG (Retrieval-Augmented Generation) Engine

This module implements the RAG pipeline for knowledge bases, combining:
- Vector similarity search on document chunks (pgvector)
- SQL queries on structured data
- Predictive analytics on extracted tables
- LLM-based synthesis with source citations

Author: EDI.ai Team
Date: 2025-12-31
"""

import logging
import os
import re
import time
from datetime import datetime
from functools import lru_cache
from typing import Dict, List, Optional, Any
import numpy as np  # Keep for type hints in old RAG methods
from sqlalchemy import create_engine, text
from langchain_community.utilities import SQLDatabase
# Note: Vector search imports removed (sentence_transformers, sklearn, qdrant_manager)
# SQL agent mode only - numpy kept for type hints only

# Setup logging
logger = logging.getLogger(__name__)


class KnowledgeBaseRAG:
    """
    Hybrid retrieval engine combining vector search, SQL, and predictive analytics.

    Features:
    - Vector similarity search on document chunks using pgvector
    - Structured data context from CSV/Excel files
    - Extracted table context from PDFs/DOCX
    - LLM synthesis with source citations
    - Query classification (RAG, SQL, Prediction, Hybrid)
    """

    def __init__(self, llm, embedding_model: str, supabase_client):
        """
        Initialize KB engine with SQL agent for structured data queries.

        Args:
            llm: LangChain LLM instance for SQL agent
            embedding_model: (Unused - kept for backwards compatibility)
            supabase_client: Supabase client for metadata access
        """
        logger.info(f"Initializing KnowledgeBaseRAG with SQL agent")

        self.llm = llm
        self.supabase = supabase_client
        self._column_cache = {}  # Cache for table column analysis

        logger.info("✅ KB engine ready (SQL agent mode)")


    def _remove_decimals_from_response(self, response: str) -> str:
        """
        Remove decimal places from numeric values in AI responses.

        Converts: "GRPS is 3159.682" → "GRPS is 3159"
        Preserves: Version numbers like "3.14.2" (word boundaries prevent matching)

        Args:
            response: AI-generated response text

        Returns:
            Response with decimals removed from standalone numbers
        """
        # Pattern matches standalone numbers with decimals
        # \b ensures word boundaries (won't match version numbers like "3.14.2")
        pattern = r'\b(\d+)\.\d+\b'

        # Replace with just the integer part
        cleaned = re.sub(pattern, r'\1', response)

        return cleaned

    def _generate_sql_plan(self, query: str, tables_desc: str, conversation_context: str, temporal_context: str) -> str:
        """
        Stage 1: SQL Planner
        Uses LLM to generate a valid SQL query string from natural language.
        """
        system_prompt = f"""You are a PostgreSQL expert query planner.
Your task is to generate a SINGLE valid SQL query to answer the user's question.

**Schema Information:**
{{tables_desc}}

**Context:**
{{conversation_context}}
{{temporal_context}}

**CRITICAL RULES:**
1. **Output ONLY the raw SQL query**. Do not use markdown, code blocks, or explanations.
2. **Dialect**: Use standard PostgreSQL.
   - **Identifiers**: You MUST double-quote ALL identifiers e.g. "Director", "Theme".
   - **Dates**: Use `EXTRACT(YEAR FROM "Date")` or `to_char("Date", 'YYYY')` for year comparisons.
   - **Relative Dates**: If the **Context** provides a "Date context" (e.g., "last 3 years = 2023 to 2026"), use the explicit years provided in the hint (e.g. `WHERE "Year" >= 2023` or `WHERE EXTRACT(YEAR FROM "Date") >= 2023`).
3. **Reasoning**:
   - **Thematic Matching (Slashed Columns)**: Columns like "Theme" often contain multiple values separated by slashes (e.g., "Crime/Thriller/Action").
     - To find "Crime Thrillers", search for *both* terms: `WHERE "Theme" ILIKE '%Crime%' AND "Theme" ILIKE '%Thriller%'`.
     - To find "Crime" specifically: `WHERE "Theme" ILIKE '%Crime%'`.
     - Always use `%word%` to ensure you match the term even if it's in the middle of a slash-separated list.
   - **Flexibility**: If a query mentions multiple genres (e.g. "Crime, Action and Drama"), use `OR` if the user implies "any", but stick to `AND` if they specify a specific sub-genre like "Crime Thriller".
   - **Contextual Selection**: Even if the query asks for a metric (e.g. "top directors"), ALWAYS select 2-3 extra context columns (e.g. "Drama", "Channel", "Theme", "Year") to allow for a richer final response.
4. **Limits**: Always limit result sets to 10 rows unless asked for more.
5. **Select Metrics**: Always SELECT the metric column used for sorting or aggregation.
"""
        from langchain.schema import HumanMessage, SystemMessage
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=query)
        ]
        
        response = self.llm.invoke(messages)
        sql = response.content.strip()
        
        # Post-processing cleanup
        import re
        sql = re.sub(r'```sql\s*', '', sql)
        sql = re.sub(r'```', '', sql)
        return sql.strip()

    def _execute_sql_query(self, db, sql_query: str) -> str:
        """
        Stage 2: SQL Executor
        Executes the SQL query deterministically against the database.
        """
        try:
            # Basic validation
            if not sql_query:
                return "Error: Empty query generated"
            
            # Allow only SELECT statements for read-only safety
            if not sql_query.upper().startswith("SELECT") and not sql_query.upper().startswith("WITH"):
                 return "Error: Only SELECT queries are allowed."

            logger.info(f"⚡ Executing SQL: {sql_query}")
            result = db.run(sql_query)
            return result
            
        except Exception as e:
            logger.error(f"❌ SQL Execution Failed: {e}")
            return f"Error executing SQL: {str(e)}"

    def _synthesize_response(self, original_query: str, sql_query: str, sql_result: str) -> str:
        """
        Stage 3: Data Analyst
        Synthesizes the SQL results into a structured natural language response.
        """
        system_prompt = """You are a detailed Data Analyst.
Transform the provided raw SQL data into a clear, structured insight.

**Response Requirements:**
1. **Natural, Professional Style**: Write a clear, comprehensive, and **info-rich** answer in normal paragraphs. Do NOT use strict section headers.
2. **Deep Contextual Analysis**: Don't just give the answer. Use the extra columns provided (Drama, Channel, Year, etc.) to explain the "background" of the results. 
   - Good: "Director X is the top performer with 500 GRPs, primarily driven by the hit drama 'Y' on [Channel] in 2024."
3. **Data Integrity**: **ALWAYS** include the specific numerical values from the raw data.
4. **Completeness**: Synthesize all relevant data points into a cohesive narrative.

**Rules:**
- Do not mention "the query result says". Just present the facts naturally.
- Focus on providing **maximum detail** from the provided rows.
- If the result is empty, clearly state that no data was found.
"""
        user_content = f"""
User Question: {{original_query}}
Executed SQL: {{sql_query}}
Raw Data Result: {{sql_result}}

Provide the structured analysis.
"""
        from langchain.schema import HumanMessage, SystemMessage
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content)
        ]
        
        response = self.llm.invoke(messages)
        return response.content.strip()

    def _analyze_table_columns(self, db_url: str, table_name: str) -> Dict[str, Any]:
        """
        Pre-analyze table columns for intelligent querying.
        Returns metadata: distinct counts, cardinality, top values.
        """
        try:
            # Check cache first
            if table_name in self._column_cache:
                logger.debug(f"⚡ Using cached analysis for table: {table_name}")
                return self._column_cache[table_name]

            engine = create_engine(db_url)
            column_metadata = {}

            with engine.connect() as conn:
                # Get total rows
                total_rows = conn.execute(
                    text(f'SELECT COUNT(*) FROM "{table_name}"')
                ).scalar()

                if total_rows == 0:
                    logger.warning(f"Table {table_name} has 0 rows")
                    return {}

                # Get columns
                result = conn.execute(text(f'SELECT * FROM "{table_name}" LIMIT 1'))
                columns = result.keys()

                # Analyze ALL columns (no limits)
                for col in columns:
                    try:
                        # Distinct count
                        distinct_count = conn.execute(
                            text(f'SELECT COUNT(DISTINCT "{col}") FROM "{table_name}"')
                        ).scalar()

                        # Top 3 values (most common)
                        top_values_result = conn.execute(text(f'''
                            SELECT "{col}", COUNT(*) as cnt
                            FROM "{table_name}"
                            WHERE "{col}" IS NOT NULL
                            GROUP BY "{col}"
                            ORDER BY cnt DESC
                            LIMIT 3
                        ''')).fetchall()

                        top_values = [str(row[0]) for row in top_values_result]

                        # Determine cardinality based on distinct count ratio
                        ratio = distinct_count / total_rows if total_rows > 0 else 0
                        if ratio > 0.9:
                            cardinality = 'unique'
                        elif distinct_count > 20:
                            cardinality = 'high'
                        elif distinct_count > 5:
                            cardinality = 'medium'
                        else:
                            cardinality = 'low'

                        column_metadata[col] = {
                            'distinct_count': distinct_count,
                            'top_values': top_values,
                            'cardinality': cardinality
                        }
                    except Exception as e:
                        logger.warning(f"Failed to analyze column {col}: {e}")
                        continue

            logger.info(f"✅ Analyzed {len(column_metadata)} columns in {table_name}")
            
            # Store in cache
            self._column_cache[table_name] = column_metadata
            return column_metadata

        except Exception as e:
            logger.error(f"❌ Failed to analyze table columns: {e}")
            return {}

        except Exception as e:
            logger.error(f"❌ Failed to analyze table columns: {e}")
            return {}

    def query_kb(
        self,
        kb_id: str,
        query: str,
        top_k: int = 5,
        conversation_history: List[Dict] = None
    ) -> Dict:
        """
        Query knowledge base using SQL agent (for structured data).

        Args:
            kb_id: Knowledge base ID
            query: User's natural language query
            top_k: Number of results (used in SQL LIMIT)
            conversation_history: List of previous messages for context (optional)

        Returns:
            Dict containing:
                - response: SQL agent answer
                - sources: SQL queries used
                - method: 'sql_agent'
        """
        logger.info(f"🤖 Querying KB {kb_id} with SQL agent: {query}")

        try:
            # Step 1: Get ALL documents in this KB (removed .limit(1))
            docs_result = self.supabase.table('kb_documents') \
                .select('id, filename, metadata') \
                .eq('kb_id', kb_id) \
                .execute()

            if not docs_result.data or len(docs_result.data) == 0:
                return {
                    'error': 'No documents found in this knowledge base',
                    'response': 'No documents found in this knowledge base. Please upload a file first.'
                }

            docs = docs_result.data

            # Step 2: Extract all Postgres tables from all documents
            tables_info = []
            for doc in docs:
                metadata = doc.get('metadata', {})
                table_name = metadata.get('postgres_table') or metadata.get('table_name')

                if table_name:
                    tables_info.append({
                        'table_name': table_name,
                        'filename': doc['filename'],
                        'columns': metadata.get('column_names', []),
                        'row_count': metadata.get('row_count', 0)
                    })

            if not tables_info:
                return {
                    'error': 'No Postgres tables found',
                    'response': 'No queryable data found in this knowledge base.'
                }

            logger.info(f"📊 Found {len(tables_info)} table(s) in KB")

            # Step 3: Initialize SQL Database Connection
            all_table_names = [t['table_name'] for t in tables_info]
            db_url = os.getenv('SUPABASE_DB_URL')
            if not db_url:
                return {'error': 'DB URL missing', 'response': 'Database connection not configured.'}

            engine = create_engine(db_url)
            db = SQLDatabase(engine, include_tables=all_table_names)

            # Step 4: Build enriched system message with column analysis
            table_descriptions = []
            for table_info in tables_info:
                table_name = table_info['table_name']
                col_metadata = self._analyze_table_columns(db_url, table_name)

                desc = f"**{table_name}** (from {table_info['filename']})\n"
                desc += f"  Rows: {table_info['row_count']}\n"
                desc += "  Columns:\n"

                for col, meta in col_metadata.items():
                    distinct = meta.get('distinct_count', 0)
                    cardinality = meta.get('cardinality', 'unknown')
                    top_values = meta.get('top_values', [])
                    sample_str = ', '.join([f'"{v}"' for v in top_values[:3]])
                    desc += f'    - "{col}": {distinct} distinct ({cardinality})'
                    if sample_str:
                        desc += f' - e.g., {sample_str}'
                    desc += '\n'
                table_descriptions.append(desc)

            tables_desc = '\n'.join(table_descriptions)

            # Step 5: Format Contexts
            rewritten_query = self._rewrite_query_with_context(query, conversation_history)
            enhanced_query = self._enhance_time_based_query(rewritten_query)
            conversation_context = self._format_conversation_context(conversation_history)
            temporal_context = self._format_temporal_context(tables_info)

            # Check for visualization
            viz_info = self._should_generate_visualization(query)
            if viz_info['should_visualize']:
                logger.info(f"📊 Visualization requested - generating viz directly")
                return self._generate_visualization_directly(
                    query=enhanced_query,
                    kb_id=kb_id,
                    tables_info=tables_info,
                    db_url=db_url,
                    suggested_chart=viz_info['suggested_chart'],
                    conversation_history=conversation_history
                )

            # Stage 1: Logic
            logger.info(f"🔄 Starting 2-Stage SQL Pipeline...")
            sql_plan = self._generate_sql_plan(enhanced_query, tables_desc, conversation_context, temporal_context)
            logger.info(f"📝 Generated SQL Plan: {sql_plan}")
            
            # Stage 2: Execute
            sql_result = self._execute_sql_query(db, sql_plan)

            # Check if execution failed (result contains "Error")
            if isinstance(sql_result, str) and sql_result.startswith("Error"):
                logger.error(f"❌ SQL Pipeline Failed: {sql_result}")
                raise Exception(f"SQL Pipeline Error: {sql_result}")

            # Stage 3: Analyst
            final_answer = self._synthesize_response(query, sql_plan, str(sql_result))
            final_answer = self._remove_decimals_from_response(final_answer)

            logger.info("✅ SQL Pipeline Completed Successfully")
            
            return {
                'response': final_answer,
                'sources': [sql_plan],
                'method': 'sql_pipeline'
            }

        except Exception as e:
            logger.error(f"❌ SQL Pipeline Error: {e}")
            agent_error = str(e)
            
            # Fallback to DataFrame analysis
            try:
                fallback_result = self._query_with_dataframe(enhanced_query, all_table_names[0])
                if fallback_result.get('approach') != 'failed':
                    logger.info(f"✅ DataFrame fallback succeeded!")
                    fallback_result['method'] = 'dataframe_fallback'
                    return fallback_result
            except Exception as fallback_err:
                logger.error(f"❌ Fallback failed: {fallback_err}")
            
            return {
                'error': agent_error,
                'response': f"I encountered errors trying multiple approaches to answer your question.\n\nCould you try rephrasing? For example: 'Show me the top 3 directors by GRPS in 2024 for crime thrillers'",
                'method': 'all_failed'
            }

        except Exception as e:
            logger.error(f"❌ Unexpected error in query_kb: {e}")
            import traceback
            traceback.print_exc()
            return {
                'error': str(e),
                'response': f"I encountered an error: {str(e)}"
            }

    def _generate_visualization_directly(
        self,
        query: str,
        kb_id: str,
        tables_info: List[Dict],
        db_url: str,
        suggested_chart: str = 'auto',
        conversation_history: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Generate visualization directly without SQL agent.

        Flow:
        1. Load table data directly into DataFrame
        2. Generate Python code to process and visualize DataFrame
        3. Execute Python code
        4. Return chart + description

        Args:
            query: User's visualization query
            kb_id: Knowledge base ID
            tables_info: List of available tables
            db_url: Database connection URL
            suggested_chart: Suggested chart type
            conversation_history: Previous conversation messages for context

        Returns:
            Response dict with visualization
        """
        try:
            from sqlalchemy import create_engine
            from kb_chart_helper import KBChartGenerator
            import pandas as pd

            logger.info(f"🎨 Direct visualization generation for: {query}")

            # Step 1: Load table data into DataFrame
            # For simplicity, use the first table (can be enhanced for multi-table)
            if not tables_info:
                return {
                    'error': 'No tables available',
                    'response': 'No data tables found in this knowledge base.'
                }

            table_info = tables_info[0]  # Use first table
            table_name = table_info['table_name']

            logger.info(f"Loading data from table: {table_name}")

            # Load full table into DataFrame
            engine = create_engine(db_url)
            df = pd.read_sql_table(table_name, engine)

            logger.info(f"Loaded {len(df)} rows, {len(df.columns)} columns")

            # Step 2: Generate Python code to process and visualize
            # Format conversation context for pronoun resolution
            conversation_context = self._format_conversation_context(conversation_history)

            # Format temporal context for date-based visualizations
            temporal_context = self._format_temporal_context([table_info])

            table_description = f"""
Table: {table_name}
From file: {table_info['filename']}
Rows: {len(df)}
Columns: {', '.join(df.columns.tolist())}

First few rows:
{df.head(3).to_string()}
"""

            viz_prompt = f"""You are a data visualization expert. Generate Python code to create a chart for this query.

Query: "{query}"
{conversation_context}
{temporal_context}

{table_description}

Instructions:
1. Libraries are ALREADY IMPORTED: plt (matplotlib.pyplot), pd (pandas), np (numpy)
2. The DataFrame 'df' is already loaded with the data
3. DO NOT include any import statements - libraries are already available
4. Generate code to:
   - Filter/process the data as needed (e.g., top 5, group by, etc.)
   - Create appropriate visualization using matplotlib
5. DO NOT use 'return' statements - assign result to 'result' variable
6. For matplotlib: create figure, plot data, set labels/title, then assign: result = plt.gcf()
7. Suggested chart type: {suggested_chart}

Code template (NO IMPORTS NEEDED):
```python
result = None
try:
    # Libraries already available: plt, pd, np, df

    plt.figure(figsize=(12, 8))

    # Process data (e.g., get top 5)
    data = df.nlargest(5, 'GRPS')

    # Create visualization
    data.plot.bar(x='Drama', y='GRPS')

    plt.title("Top 5 Dramas by GRPs")
    plt.xlabel("Drama")
    plt.ylabel("GRPs")
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()

    result = plt.gcf()
except Exception as e:
    print(f"Error: {str(e)}")
    result = f"Error: {str(e)}"
```

Generate ONLY the Python code with NO import statements."""

            logger.info("Generating Python visualization code...")
            code_response = self.llm.invoke(viz_prompt)
            code = code_response.content.strip()

            # Clean code
            code = code.replace('```python', '').replace('```', '').strip()

            # Remove any import statements (libraries already available)
            code_lines = code.split('\n')
            filtered_lines = []
            for line in code_lines:
                if line.strip().startswith(('import ', 'from ')):
                    logger.debug(f"Filtering out import: {line}")
                    continue
                filtered_lines.append(line)
            code = '\n'.join(filtered_lines)

            logger.info(f"Generated code length: {len(code)}")
            logger.debug(f"Code:\n{code}")

            # Step 3: Execute Python code
            chart_gen = KBChartGenerator(llm=self.llm)
            visualization = chart_gen._execute_chart_code(code, df)

            if not visualization:
                logger.error("Chart generation failed")
                return {
                    'error': 'Chart generation failed',
                    'response': "I couldn't generate the visualization."
                }

            logger.info(f"✅ Visualization created: {visualization['filename']}")

            # Step 4: Generate description
            description_prompt = f"""Generate a brief (1-2 sentences) description of this visualization.

Query: "{query}"
Data: {len(df)} total rows
Chart shows the processed/filtered data

Provide ONLY the description text."""

            desc_response = self.llm.invoke(description_prompt)
            description = desc_response.content.strip().replace('**', '').replace('*', '').strip('"').strip("'")
            description = self._remove_decimals_from_response(description)

            # Step 5: Generate text summary
            summary_prompt = f"""Based on this query and data, provide a brief (2-3 sentences) summary.

Query: {query}
Total rows: {len(df)}
Columns: {', '.join(df.columns.tolist())}

Provide ONLY the summary text."""

            summary_response = self.llm.invoke(summary_prompt)
            summary = summary_response.content.strip()
            summary = self._remove_decimals_from_response(summary)

            # Build response
            response_dict = {
                'response': summary,
                'method': 'direct_visualization',
                'tables_queried': [table_info['filename']],
                'visualization': {
                    'type': visualization['type'],
                    'path': f"/static/visualizations/{visualization['filename']}",
                    'description': description
                }
            }

            return response_dict

        except Exception as e:
            logger.error(f"❌ Direct visualization error: {e}")
            logger.exception("Full traceback:")
            return {
                'error': str(e),
                'response': f"I encountered an error generating the visualization: {str(e)}"
            }

    def _query_with_dataframe(self, query: str, table_name: str, max_retries: int = 3) -> dict:
        """
        Fallback approach: Load data into pandas and generate Python code instead of SQL.

        This is more reliable than SQL generation because:
        - Python syntax errors are caught before execution with ast.parse()
        - Error messages are clearer for LLMs to understand
        - Retry loop is simpler with better error feedback
        - Already proven working in visualization code (lines 756-801)

        Args:
            query: User's natural language query
            table_name: Name of the table to load
            max_retries: Maximum number of retry attempts

        Returns:
            Dict with response, approach='dataframe', and generated code
        """
        import pandas as pd
        import ast

        try:
            # Load data into DataFrame
            logger.info(f"📊 Loading table '{table_name}' into DataFrame for fallback approach")
            df = pd.read_sql_table(table_name, self.engine)
            logger.info(f"✅ Loaded {len(df)} rows with {len(df.columns)} columns")

            # Get sample data for better code generation
            sample_data = df.head(3).to_string(max_colwidth=50)

            error_feedback = None
            generated_code = None

            for attempt in range(max_retries):
                logger.info(f"🔄 DataFrame query attempt {attempt + 1}/{max_retries}")

                # Generate Python code with LLM - enhanced prompt with examples
                prompt = f"""Generate Python code to answer this query using pandas.

DataFrame 'df' is already loaded with {len(df)} rows.

Columns: {list(df.columns)}

Sample data:
{sample_data}

Query: "{query}"

{"Previous attempt failed with error: " + error_feedback if error_feedback else ""}

Requirements:
1. Use ONLY pandas operations on the 'df' variable
2. Store the final answer in a variable called 'result'
3. Make 'result' a simple Python dict with 'data' key containing the answer
4. Use exact column names from the list above (case-sensitive)
5. NO file operations, NO imports, NO dangerous operations
6. Keep code simple and safe
7. For year filtering, use: df[df['Lunch date'].dt.year == 2024]
8. For string matching, use case-insensitive: df[df['Theme'].str.contains('Crime', case=False, na=False)]

Common patterns:
- Top N: df.groupby('Director')['GRPS'].sum().nlargest(3).to_dict()
- Filter + aggregate: df[df['Theme']=='Crime/Thriller'].groupby('Director')['GRPS'].sum().nlargest(3).to_dict()
- Year filter: df[df['Lunch date'].dt.year == 2024]
- Count: df.groupby('Director').size().to_dict()

Generate ONLY the Python code, no markdown, no explanation."""

                response = self.llm.invoke(prompt)
                code = response.content.strip()

                # Extract code if wrapped in markdown
                if '```python' in code:
                    code = code.split('```python')[1].split('```')[0].strip()
                elif '```' in code:
                    code = code.split('```')[1].split('```')[0].strip()

                generated_code = code
                logger.info(f"Generated code:\n{code}")

                # Validate syntax BEFORE execution
                try:
                    ast.parse(code)
                    logger.info("✅ Code syntax is valid")
                except SyntaxError as e:
                    error_feedback = f"Syntax error on line {e.lineno}: {e.msg}"
                    logger.warning(f"❌ Syntax validation failed: {error_feedback}")
                    continue

                # Execute code safely with restricted scope
                local_vars = {"df": df, "pd": pd, "np": np}
                try:
                    exec(code, {"__builtins__": {}}, local_vars)
                    result = local_vars.get('result', {})

                    # Validate result structure
                    if not isinstance(result, dict) or 'data' not in result:
                        error_feedback = "Result must be a dict with 'data' key"
                        logger.warning(f"❌ Invalid result structure: {error_feedback}")
                        continue

                    logger.info(f"✅ DataFrame query succeeded on attempt {attempt + 1}")

                    # Format results into natural language response
                    data = result['data']

                    # Ask LLM to format the data into a nice response
                    format_prompt = f"""Format this query result into a natural language response.

Original query: "{query}"

Result data:
{data}

Provide a clear, concise response using the structured format:

**Summary:**
[Direct answer in 1-2 sentences]

**Key Metrics:** (or Rankings/Comparison/Results as appropriate)
- Point 1: [value] ([context if relevant])
- Point 2: [value] ([context if relevant])
- Point 3+: [additional points as needed]

**Analysis:**
[Contextual paragraph providing insights or context]"""

                    format_response = self.llm.invoke(format_prompt)
                    formatted_answer = format_response.content.strip()

                    return {
                        "response": formatted_answer,
                        "approach": "dataframe",
                        "code": generated_code,
                        "sql_queries": []  # No SQL used
                    }

                except KeyError as e:
                    error_feedback = f"Column not found: {e}. Available columns: {list(df.columns)}"
                    logger.warning(f"❌ Execution failed: {error_feedback}")
                    continue

                except Exception as e:
                    error_feedback = f"{type(e).__name__}: {str(e)}"
                    logger.warning(f"❌ Execution failed: {error_feedback}")
                    continue

            # If all retries failed - provide a GUARANTEED fallback with basic info
            logger.warning(f"⚠️ DataFrame code generation failed after {max_retries} attempts. Trying basic fallback...")

            try:
                # GUARANTEED FALLBACK: Provide basic data summary
                summary_data = {
                    "total_rows": len(df),
                    "columns": list(df.columns),
                    "sample": df.head(5).to_dict('records')
                }

                fallback_prompt = f"""The query "{query}" could not be processed automatically.

However, here is the available data structure:
- Total rows: {summary_data['total_rows']}
- Columns: {summary_data['columns']}

Provide a helpful response explaining what data is available and suggest how the user could rephrase their query.
Be specific about the columns they can query (like Director, GRPS, Theme, etc.)."""

                fallback_response = self.llm.invoke(fallback_prompt)

                return {
                    "response": fallback_response.content.strip(),
                    "approach": "fallback_summary",
                    "error": error_feedback,
                    "available_columns": list(df.columns)
                }

            except Exception as e:
                logger.error(f"❌ Even fallback summary failed: {e}")
                # Still provide SOMETHING - never return 'failed' when we have basic info
                return {
                    "response": f"I had trouble processing this query. The data has {len(df)} rows with these columns: {', '.join(list(df.columns)[:10])}...\n\nCould you rephrase? For example: 'Show me the top 3 directors by GRPS in 2024'",
                    "approach": "basic_info",  # Changed from 'failed' - we ARE providing useful info
                    "error": error_feedback,
                    "code": generated_code
                }

        except Exception as e:
            logger.error(f"❌ DataFrame query error: {e}")
            logger.exception("Full traceback:")
            return {
                "response": f"I encountered an error loading the data: {str(e)}",
                "approach": "failed",
                "error": str(e)
            }

    def _format_conversation_context(self, conversation_history: List[Dict]) -> str:
        """
        Format conversation history for SQL agent context.

        Args:
            conversation_history: List of message dicts with 'role' and 'content'

        Returns:
            Formatted context string for SQL agent
        """
        if not conversation_history or len(conversation_history) == 0:
            return ""

        context = "\n**Recent Conversation Context:**\n"
        for msg in conversation_history[-6:]:  # Last 3 exchanges (6 messages)
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            # Truncate long messages
            preview = content[:150] + '...' if len(content) > 150 else content
            context += f"- {role.capitalize()}: {preview}\n"

        context += "\n**IMPORTANT:** Use this context to resolve pronouns (she/he/they/their/it) and references (the writer/that channel/those dramas) in the current query.\n"
        return context

    def _rewrite_query_with_context(self, query: str, conversation_history: List[Dict]) -> str:
        """
        Rewrite vague follow-up queries to explicit queries using conversation context.
        
        This solves the problem of queries like "tell me more about it" where "it" refers
        to a subject mentioned in previous messages. The LLM expands these to full queries.
        
        Args:
            query: User's current query (may be vague with pronouns)
            conversation_history: List of previous messages for context
            
        Returns:
            Rewritten query with pronouns resolved, or original if no rewriting needed
        """
        # Skip rewriting if no conversation history
        if not conversation_history or len(conversation_history) == 0:
            return query
        
        # Quick check: does query contain vague references that need resolution?
        vague_patterns = [
            'it', 'this', 'that', 'them', 'they', 'their', 'these', 'those',
            'more about', 'tell me more', 'what about', 'how about',
            'the same', 'similar', 'like that', 'the one', 'which one'
        ]
        
        query_lower = query.lower()
        needs_rewriting = any(pattern in query_lower for pattern in vague_patterns)
        
        # Also check for very short queries (likely follow-ups)
        if len(query.split()) <= 5:
            needs_rewriting = True
        
        if not needs_rewriting:
            logger.info(f"✅ Query doesn't need rewriting: '{query}'")
            return query
        
        logger.info(f"🔄 Query may need rewriting: '{query}'")
        
        try:
            # Format recent conversation for context
            context_messages = []
            for msg in conversation_history[-6:]:  # Last 3 exchanges
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
                # Use more content for rewriting (300 chars vs 150)
                preview = content[:300] + '...' if len(content) > 300 else content
                context_messages.append(f"{role.upper()}: {preview}")
            
            conversation_text = "\n".join(context_messages)
            
            rewrite_prompt = f"""You are a query rewriter. Your task is to expand vague follow-up questions into clear, explicit queries.

CONVERSATION HISTORY:
{conversation_text}

CURRENT USER QUERY: "{query}"

CRITICAL RULES:
1. ONLY use entity names (people, channels, shows, etc.) that appear in the conversation history above
2. DO NOT add new entity names, channel names, or keywords that weren't explicitly mentioned
3. If the query is already clear and explicit, return it UNCHANGED

TASK:
1. If the current query contains pronouns (it, they, them, this, that, etc.) or vague references, replace ONLY those pronouns with the specific subject from the conversation
2. DO NOT add any information beyond resolving pronouns - preserve the user's query exactly otherwise
3. If the query is already explicit and clear, return it unchanged

EXAMPLES:
Positive examples (expand pronouns):
- History mentions "Meri Zaat Zarra-e-Benishan" + Query "tell me more about it" → "tell me more about Meri Zaat Zarra-e-Benishan"
- History mentions "Umera Ahmed" + Query "what else did she write" → "what other dramas did Umera Ahmed write"
- History mentions "top 5 dramas" + Query "show their ratings" → "show ratings for the top 5 dramas"

Negative examples (don't add new entities):
- Query "top directors by GRPS in crime dramas" (already explicit) → "top directors by GRPS in crime dramas" (UNCHANGED)
- History doesn't mention channel + Query "best writers last year" → "best writers last year" (UNCHANGED - don't add "Geo Entertainment")
- Query "what are crime dramas" (no pronouns) → "what are crime dramas" (UNCHANGED)

Return ONLY the rewritten query, nothing else. No quotes, no explanation."""

            response = self.llm.invoke(rewrite_prompt)
            rewritten = response.content.strip().strip('"').strip("'")

            # Check for hallucinated entities (safety check)
            def extract_capitalized_entities(text):
                """Extract potential entity names (capitalized multi-word phrases)"""
                return set(re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+', text))

            query_entities = extract_capitalized_entities(query)
            rewritten_entities = extract_capitalized_entities(rewritten)
            new_entities = rewritten_entities - query_entities

            # Check if new entities appear in conversation history
            if new_entities:
                history_text = "\n".join([msg.get('content', '') for msg in conversation_history])
                hallucinated = [e for e in new_entities if e not in history_text]

                if hallucinated:
                    logger.warning(f"⚠️ Rewriter added entities not in history: {hallucinated}. Using original query.")
                    return query

            # Validate rewritten query
            if rewritten and len(rewritten) > 3 and len(rewritten) < 500:
                logger.info(f"✅ Query rewritten: '{query}' → '{rewritten}'")
                return rewritten
            else:
                logger.warning(f"Rewriting produced invalid result, using original query")
                return query
                
        except Exception as e:
            logger.error(f"❌ Query rewriting failed: {e}. Using original query.")
            return query

    def _enhance_time_based_query(self, query: str) -> str:
        """
        Preprocess query to add calculated date hints for time-based phrases.

        This helps the LLM by providing explicit date ranges instead of requiring
        it to calculate "last N years" or "this year" on its own.

        Args:
            query: User's original query

        Returns:
            Enhanced query with date hints appended
        """
        current_date = datetime.now()
        current_year = current_date.year
        current_date_str = current_date.strftime('%Y-%m-%d')

        enhanced_query = query
        hints = []

        # Pattern 1: "last N years"
        if match := re.search(r'last (\d+) years?', query, re.IGNORECASE):
            n = int(match.group(1))
            start_year = current_year - n
            hints.append(f"last {n} year(s) = {start_year} to {current_year}")

        # Pattern 2: "last N months"
        if match := re.search(r'last (\d+) months?', query, re.IGNORECASE):
            n = int(match.group(1))
            # Calculate start month (handle year rollover)
            start_month = current_date.month - n
            start_year_adj = current_year
            if start_month <= 0:
                start_year_adj = current_year + (start_month // 12) - 1
                start_month = 12 + (start_month % 12)
            start_date = current_date.replace(year=start_year_adj, month=start_month)
            hints.append(f"last {n} month(s) = {start_date.strftime('%Y-%m')} to {current_date.strftime('%Y-%m')}")

        # Pattern 3: "this year"
        if re.search(r'\bthis year\b', query, re.IGNORECASE):
            hints.append(f"this year = {current_year}")

        # Pattern 4: "recent" or "recently"
        if re.search(r'\brecent(ly)?\b', query, re.IGNORECASE):
            hints.append(f"recent = closer to {current_date_str}")

        # Pattern 5: "in 2024" or "year 2024" - extract the year for context
        if match := re.search(r'\b(in|year) (20\d{2})\b', query, re.IGNORECASE):
            year = match.group(2)
            hints.append(f"specific year = {year}")

        # Append hints to query if any were found
        if hints:
            hint_text = " [Date context: " + "; ".join(hints) + "]"
            enhanced_query = query + hint_text
            logger.debug(f"Enhanced time-based query: {enhanced_query}")

        return enhanced_query

    def _format_temporal_context(self, tables_info: List[Dict] = None) -> str:
        """
        Format current date/time and dataset statistics context for SQL agent.

        Args:
            tables_info: Optional list of table metadata (for statistics extraction)

        Returns:
            Formatted temporal and statistical context string
        """
        current_date = datetime.now()
        current_year = current_date.year
        current_date_str = current_date.strftime('%Y-%m-%d')

        context = f"\n**Temporal Context:**\n"
        context += f"- Current Date: {current_date_str}\n"
        context += f"- Current Year: {current_year}\n"
        context += f"- When user asks for 'last N years', calculate from {current_year} backwards\n"
        context += f"- 'Recent' or 'latest' means closer to {current_date_str}\n"
        context += f"\n**PostgreSQL Date Functions:**\n"
        context += f"- For 'last N years': Use \"date_column\" >= NOW() - INTERVAL 'N years'\n"
        context += f"- Current timestamp: NOW() or CURRENT_DATE\n"
        context += f"- Extract year: EXTRACT(YEAR FROM \"date_column\") or DATE_PART('year', \"date_column\")\n"

        # Add dataset statistics if available (info-rich enhancement)
        if tables_info and len(tables_info) > 0:
            context += f"\n**Dataset Statistics:**\n"
            for table_info in tables_info:
                table_name = table_info.get('table_name', 'unknown')
                row_count = table_info.get('row_count', 'unknown')
                filename = table_info.get('filename', 'unknown')

                context += f"- Table '{table_name}' from {filename}: {row_count} rows\n"

                # Try to identify business domain from filename
                filename_lower = filename.lower()
                if 'drama' in filename_lower or 'tv' in filename_lower:
                    context += f"- Domain: Pakistani TV drama industry data\n"

                # Note: Could be enhanced to extract actual date ranges by querying min/max dates
                # For now, provide general guidance
                columns = table_info.get('columns', [])
                date_columns = [col for col in columns if 'date' in col.lower() or 'year' in col.lower()]
                if date_columns:
                    context += f"- Date columns available: {', '.join(date_columns)}\n"

        return context

    def _should_generate_visualization(self, query: str) -> Dict[str, Any]:
        """
        Detect if query explicitly requests visualization.

        User requirement: Only trigger on explicit keywords like
        "visualize", "show", "chart", "plot", etc.

        NOT automatic for queries like "top 5" without viz keywords.

        Returns:
            {
                'should_visualize': bool,
                'suggested_chart': str  # 'bar', 'line', 'pie', 'scatter', 'auto'
            }
        """
        query_lower = query.lower()

        # EXPLICIT visualization request keywords ONLY
        explicit_viz_keywords = [
            'visualize', 'visualization', 'visualise',
            'chart', 'plot', 'graph', 'diagram',
            'show', 'display', 'draw', 'create a',
            'generate a', 'make a', 'build a',
            'histogram', 'bar chart', 'line chart', 'pie chart',
            'scatter plot'
        ]

        # Check if query contains explicit visualization request
        should_viz = any(kw in query_lower for kw in explicit_viz_keywords)

        # Suggest chart type based on keywords
        suggested_chart = 'auto'  # Default: Let LLM decide

        if should_viz:
            if 'pie' in query_lower or 'proportion' in query_lower:
                suggested_chart = 'pie'
            elif 'line' in query_lower or 'trend' in query_lower or 'over time' in query_lower:
                suggested_chart = 'line'
            elif 'bar' in query_lower or 'histogram' in query_lower:
                suggested_chart = 'bar'
            elif 'scatter' in query_lower:
                suggested_chart = 'scatter'

        return {
            'should_visualize': should_viz,
            'suggested_chart': suggested_chart
        }

    def _extract_sql_output(self, intermediate_steps) -> Optional[str]:
        """
        Extract SQL query results from agent's tool execution steps.

        Args:
            intermediate_steps: Agent's intermediate execution steps

        Returns:
            SQL output as string (accepts markdown table, Python list, or raw text)
        """
        for step in intermediate_steps:
            if isinstance(step, tuple) and len(step) > 1:
                observation = step[1]  # Tool output
                if isinstance(observation, str) and observation.strip():
                    # Accept any non-empty SQL output
                    # Could be: markdown table (|...|), Python list [(...), (...)], or plain text
                    # The chart helper will parse it
                    if any(char in observation for char in ['|', '[', '(', ',']):
                        return observation

        return None

    def _generate_query_embedding(self, query: str) -> np.ndarray:
        """
        Generate embedding for user query.

        Args:
            query: User's question

        Returns:
            NumPy array (384-dimensional)
        """
        logger.debug(f"Generating embedding for query: {query[:50]}...")

        try:
            embedding = self.embedding_model.encode([query], convert_to_numpy=True)[0]
            return embedding
        except Exception as e:
            logger.error(f"Error generating query embedding: {e}")
            raise

    def _vector_search(self, kb_id: str, query_embedding: np.ndarray, top_k: int,
                      query_text: str = None, use_enhancement: bool = True) -> List[Dict]:
        """
        Enhanced vector similarity search with query expansion, reranking, and MMR.

        Pipeline:
        1. Query expansion (if query_text provided) - generate multiple query variants
        2. Multi-query retrieval - retrieve more candidates from all variants
        3. Cross-encoder reranking - score candidates for true relevance
        4. MMR diversity - select diverse top_k results

        Args:
            kb_id: Knowledge base ID
            query_embedding: Query embedding vector
            top_k: Number of final results to return
            query_text: Original query text (needed for expansion and reranking)
            use_enhancement: If False, use basic vector search only

        Returns:
            List of dicts with id, document_id, content, chunk_metadata, similarity, rerank_score
        """
        logger.debug(f"Performing vector search for KB {kb_id}, top_k={top_k}, enhanced={use_enhancement}")

        # Basic search if enhancement disabled or query_text not provided
        if not use_enhancement or not query_text:
            return self._basic_vector_search(kb_id, query_embedding, top_k)

        try:
            # Step 1: Query expansion - generate query variants
            query_variants = self._expand_query(query_text)
            logger.info(f"Generated {len(query_variants)} query variants")

            # Step 2: Multi-query retrieval - retrieve candidates from all variants
            # Retrieve 3x top_k to ensure diversity after reranking
            candidates_per_query = max(top_k * 3, 15)
            all_candidates = {}  # Use dict to deduplicate by chunk ID

            for variant in query_variants:
                variant_embedding = self.embedding_model.encode([variant], convert_to_numpy=True)[0]

                # Search Qdrant for this variant
                qdrant_results = self.qdrant.search_similar(
                    kb_id=kb_id,
                    query_embedding=variant_embedding,
                    top_k=candidates_per_query
                )

                # Convert Qdrant results and deduplicate
                for result in qdrant_results:
                    chunk = {
                        'id': result['id'],
                        'document_id': result['document_id'],
                        'content': result['content'],
                        'similarity': result['score'],
                        'chunk_metadata': result.get('metadata', {})
                    }
                    chunk_id = chunk.get('id')
                    # Keep chunk with highest similarity if duplicate
                    if chunk_id not in all_candidates or chunk.get('similarity', 0) > all_candidates[chunk_id].get('similarity', 0):
                        all_candidates[chunk_id] = chunk

            unique_candidates = list(all_candidates.values())
            logger.info(f"Multi-query retrieval found {len(unique_candidates)} unique candidates")

            if not unique_candidates:
                return []

            # Step 3: Cross-encoder reranking - get true relevance scores
            # Rerank with 2x top_k to provide good candidates for MMR
            reranked = self._rerank_results(query_text, unique_candidates, top_k=min(top_k * 2, len(unique_candidates)))
            logger.info(f"Reranked to {len(reranked)} candidates")

            # Step 4: MMR diversity - select diverse final results
            # Use original query embedding for MMR
            diverse_results = self._apply_mmr(query_embedding, reranked, lambda_param=0.7, top_k=top_k)
            logger.info(f"MMR selected {len(diverse_results)} diverse results")

            return diverse_results

        except Exception as e:
            logger.error(f"Error in enhanced vector search: {e}. Falling back to basic search.")
            # Fallback to basic search on error
            return self._basic_vector_search(kb_id, query_embedding, top_k)

    def _basic_vector_search(self, kb_id: str, query_embedding: np.ndarray, top_k: int) -> List[Dict]:
        """
        Vector similarity search using Qdrant for high-performance retrieval.

        Args:
            kb_id: Knowledge base ID
            query_embedding: Query embedding vector (384-dimensional)
            top_k: Number of results to return

        Returns:
            List of dicts with id, document_id, content, chunk_metadata, similarity
        """
        logger.debug(f"🔍 Performing Qdrant vector search for KB {kb_id}, top_k={top_k}")

        try:
            # Search in Qdrant
            results = self.qdrant.search_similar(
                kb_id=kb_id,
                query_embedding=query_embedding,
                top_k=top_k
            )

            # Format results to match expected structure
            chunks = []
            for result in results:
                chunk = {
                    'id': result['id'],
                    'document_id': result['document_id'],
                    'content': result['content'],
                    'similarity': result['score'],  # Qdrant returns 'score', rename to 'similarity'
                    'chunk_metadata': result.get('metadata', {})
                }
                chunks.append(chunk)

            logger.info(f"✅ Qdrant returned {len(chunks)} results")
            return chunks

        except Exception as e:
            logger.error(f"❌ Error in Qdrant search: {e}")
            # Return empty list on error instead of failing completely
            return []

    def _get_structured_data_context(self, kb_id: str) -> Dict:
        """
        Fetch metadata about available structured datasets in KB.

        This provides context about what data is available for SQL queries
        and predictive analytics.

        Args:
            kb_id: Knowledge base ID

        Returns:
            Dict with structured_files and extracted_tables lists
        """
        logger.debug(f"Fetching structured data context for KB {kb_id}")

        try:
            # Fetch structured data files (CSV, Excel)
            struct_data_result = self.supabase.table('kb_structured_data') \
                .select('*') \
                .eq('kb_id', kb_id) \
                .execute()

            # Fetch extracted tables from documents
            extracted_tables_result = self.supabase.table('kb_extracted_tables') \
                .select('*') \
                .eq('kb_id', kb_id) \
                .execute()

            structured_files = struct_data_result.data if struct_data_result.data else []
            extracted_tables = extracted_tables_result.data if extracted_tables_result.data else []

            logger.info(f"Found {len(structured_files)} structured files, {len(extracted_tables)} extracted tables")

            return {
                'structured_files': structured_files,
                'extracted_tables': extracted_tables
            }

        except Exception as e:
            logger.error(f"Error fetching structured data context: {e}")
            return {'structured_files': [], 'extracted_tables': []}

    def _query_structured_data(
        self,
        query: str,
        structured_ctx: Dict,
        conversation_history: List[Dict] = None
    ) -> str:
        """
        Generate and execute SQL queries on structured data files.

        ALWAYS executes SQL when structured data exists to ensure data is accessible.

        Args:
            query: User's question
            structured_ctx: Context about structured data files
            conversation_history: List of previous messages for pronoun/entity resolution
        """
        results = []

        # If no structured files, skip
        if not structured_ctx['structured_files']:
            return ""

        # Preprocess query to add date hints
        enhanced_query = self._enhance_time_based_query(query)

        # Always try SQL when we have structured data files
        # This ensures Excel/CSV data is always searchable
        logger.info(f"Querying {len(structured_ctx['structured_files'])} structured files with SQL")

        for file_info in structured_ctx['structured_files']:
            try:
                filename = file_info.get('filename')
                db_path = file_info.get('temp_db_path')
                columns = file_info.get('column_names', [])
                
                # Validate database path exists
                if not db_path or not os.path.exists(db_path):
                    logger.warning(f"Database path not found: {db_path}")
                    continue

                # Fetch sample data to show LLM what's in each column
                engine = create_engine(f'sqlite:///{db_path}')
                column_info_list = []
                try:
                    with engine.connect() as conn:
                        sample_result = conn.execute(text('SELECT * FROM data_table LIMIT 2'))
                        sample_rows = sample_result.fetchall()

                        # Build column descriptions with sample values
                        for i, col in enumerate(columns):
                            sample_vals = [str(row[i])[:50] for row in sample_rows if row[i] is not None]
                            if sample_vals:
                                column_info_list.append(f'  - {col} (e.g., "{sample_vals[0]}")')
                            else:
                                column_info_list.append(f'  - {col}')

                        column_info = '\n'.join(column_info_list)
                except Exception as e:
                    logger.warning(f"Failed to fetch sample data: {e}")
                    # Fallback to just column names
                    column_info = '\n'.join([f'  - {col}' for col in columns])

                # Build conversation context string for SQL generation
                conversation_context = ""
                if conversation_history and len(conversation_history) > 0:
                    conversation_context = "Recent Conversation:\n"
                    for msg in conversation_history[-6:]:  # Last 3 exchanges (6 messages)
                        role = msg.get('role', 'unknown')
                        content = msg.get('content', '')
                        # Truncate long messages
                        content_preview = content[:200] + '...' if len(content) > 200 else content
                        conversation_context += f"{role.capitalize()}: {content_preview}\n"
                    conversation_context += "\n"

                # Generate temporal context
                current_date = datetime.now().strftime('%Y-%m-%d')
                current_year = datetime.now().year
                temporal_info = f"""Current Date: {current_date}
Current Year: {current_year}
For 'last N years', calculate from {current_year} backwards.

SQLite Date Syntax:
- For 'last N years': Use strftime('%Y', "date_column") >= '{current_year - 3}' (example for last 3 years)
- Extract year: strftime('%Y', "date_column")

"""

                # Generate SQL using LLM with improved prompt showing sample data
                prompt = f"""You are a SQL expert. Generate a SQLite query for this question.

{temporal_info}{conversation_context}Table: data_table
File: {filename}

Columns and sample values:
{column_info}

User Question: {enhanced_query}

General Guidelines:
- Use column names EXACTLY as shown (with spaces, hyphens, etc.) in double quotes
- For date columns, extract year using: strftime('%Y', "column_name")
- Analyze the user's question to determine which columns to filter/group/aggregate
- Use appropriate SQL functions (SUM, COUNT, AVG, etc.) based on the question
- Apply LIMIT based on question context ("top 5" = LIMIT 5, "top 10" = LIMIT 10, etc.)
- Make text searches case-insensitive using LOWER()
- Use LIKE with wildcards for text matching: WHERE LOWER("column") LIKE '%keyword%'

IMPORTANT - Conversation Context:
- If the user uses pronouns (she, he, it, they), look at the recent conversation to resolve them
- If the user says "the writer" or "the drama" or "that channel", use context to identify what they're referring to
- Build upon previous questions and answers - the conversation flows together

Examples:
Previous: "Huma Hina Nafees has the highest GRPs"
Current: "which channel has she released most dramas on"
→ Resolve "she" = "Huma Hina Nafees", generate: SELECT "Channel", COUNT(*) FROM data_table WHERE LOWER("Writer") LIKE '%huma hina nafees%' OR LOWER("Writer 2") LIKE '%huma hina nafees%' OR LOWER("Writer 3") LIKE '%huma hina nafees%' GROUP BY "Channel" ORDER BY COUNT(*) DESC LIMIT 1

Return ONLY the SQL query, no markdown or explanation.
"""
                logger.info(f"Generating SQL for query: {query}")
                response = self.llm.invoke(prompt)
                sql_query = response.content if hasattr(response, 'content') else str(response)
                logger.info(f"Generated SQL: {sql_query}")
                
                # Clean SQL
                sql_query = sql_query.replace('```sql', '').replace('```', '').strip()
                
                # Execute
                engine = create_engine(f'sqlite:///{db_path}')
                with engine.connect() as conn:
                    result = conn.execute(text(sql_query))
                    rows = result.fetchall()
                    keys = result.keys()
                    
                    if rows:
                        results.append(f"Results from {filename}:")
                        # Format as markdown table or list
                        for row in rows[:5]: # Limit rows
                            row_dict = dict(zip(keys, row))
                            results.append(str(row_dict))
                        if len(rows) > 5:
                            results.append(f"... (+{len(rows)-5} more rows)")
                            
            except Exception as e:
                logger.warning(f"Failed to query {filename}: {e}")
                continue
                
        return "\n".join(results)

    def _build_context(self, chunks: List[Dict], structured_ctx: Dict, sql_results: str = "") -> str:
        """
        Combine document chunks, structured data metadata, and SQL results into context string.

        Args:
            chunks: List of retrieved document chunks
            structured_ctx: Structured data context
            sql_results: Results from executed SQL queries

        Returns:
            Formatted context string for LLM
        """
        logger.debug("Building combined context")

        context = ""

        # Add document excerpts
        if chunks:
            context += "=== RELEVANT DOCUMENT EXCERPTS ===\n\n"
            for idx, chunk in enumerate(chunks, start=1):
                content = chunk.get('content', '')
                similarity = chunk.get('similarity', 0)

                # Truncate very long chunks
                if len(content) > 500:
                    content = content[:500] + "..."

                context += f"[Source {idx}] (Relevance: {similarity:.2f})\n{content}\n\n"

        # Add structured data context
        if structured_ctx['structured_files']:
            context += "\n=== AVAILABLE DATASETS ===\n"
            for ds in structured_ctx['structured_files']:
                filename = ds.get('filename', 'Unknown')
                row_count = ds.get('row_count', 0)
                column_names = ds.get('column_names', [])

                context += f"- **{filename}**: {row_count:,} rows\n"
                context += f"  Columns: {', '.join(column_names[:10])}"  # Limit to first 10 columns
                if len(column_names) > 10:
                    context += f" ... (+{len(column_names) - 10} more)"
                context += "\n"

        # Add extracted tables context
        if structured_ctx['extracted_tables']:
            context += "\n=== EXTRACTED TABLES FROM DOCUMENTS ===\n"
            for tbl in structured_ctx['extracted_tables']:
                page = tbl.get('page_number', '?')
                table_idx = tbl.get('table_index', 0)
                row_count = tbl.get('row_count', 0)
                columns = tbl.get('column_names', [])

                context += f"- Table {table_idx} from page {page}: {row_count} rows\n"
                context += f"  Columns: {', '.join(columns)}\n"

        # Add SQL query results
        if sql_results:
             context += "\n=== STRUCTURED DATA QUERY RESULTS ===\n"
             context += sql_results
             context += "\n"

        logger.debug(f"Built context of {len(context)} characters")
        return context

    def _build_context_from_chunks(self, chunks: List[Dict]) -> str:
        """
        Build context string from retrieved chunks only (pure RAG).

        Args:
            chunks: List of retrieved document chunks

        Returns:
            Formatted context string
        """
        logger.debug("Building context from chunks (pure RAG)")

        context = ""

        if chunks:
            context += "=== RELEVANT INFORMATION ===\n\n"
            for idx, chunk in enumerate(chunks, start=1):
                content = chunk.get('content', '')
                similarity = chunk.get('similarity', 0)
                metadata = chunk.get('chunk_metadata', {})

                # Show relevance score
                context += f"[Source {idx}] (Relevance: {similarity:.2f})\n"

                # Add filename if available
                filename = metadata.get('filename')
                if filename:
                    context += f"From: {filename}\n"

                context += f"{content}\n\n"
        else:
            context = "No relevant information found in the knowledge base."

        logger.debug(f"Built context of {len(context)} characters from {len(chunks)} chunks")
        return context

    def _estimate_token_count(self, chunks: List[Dict]) -> int:
        """
        Estimate total tokens needed to send chunks as context to LLM.

        Rule of thumb: 1 token ≈ 4 characters for English text

        Args:
            chunks: Retrieved document chunks

        Returns:
            Estimated token count
        """
        total_chars = 0

        # Count characters in chunk content
        for chunk in chunks:
            content = chunk.get('content', '')
            total_chars += len(content)

        # Add overhead for formatting (headers, labels, spacing)
        # Rough estimate: 100 chars per chunk for formatting
        formatting_overhead = len(chunks) * 100
        total_chars += formatting_overhead

        # Convert to tokens (conservative estimate: 1 token = 4 chars)
        estimated_tokens = total_chars // 4

        logger.debug(f"Estimated {estimated_tokens} tokens for {len(chunks)} chunks")
        return estimated_tokens

    def _generate_response(
        self,
        query: str,
        context: str,
        chunks: List[Dict],
        conversation_history: List[Dict] = None
    ) -> str:
        """
        Generate LLM response with context and source citations.

        Args:
            query: User's query
            context: Combined context string
            chunks: Retrieved chunks for citation
            conversation_history: List of previous messages for context

        Returns:
            LLM-generated response with citations
        """
        logger.debug("Generating LLM response")

        try:
            # Build conversation context for response generation
            conversation_context_str = ""
            if conversation_history and len(conversation_history) > 0:
                conversation_context_str = "Recent Conversation:\n"
                for msg in conversation_history[-4:]:  # Last 2 exchanges (4 messages)
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')[:150]  # Truncate to 150 chars
                    conversation_context_str += f"{role.capitalize()}: {content}\n"
                conversation_context_str += "\n"

            # Build prompt with context
            prompt = f"""You are a helpful AI assistant. Answer the user's question in a natural, conversational way.

{conversation_context_str}**Available Data:**
{context}

**User Question:** {query}

**Instructions:**
1. Answer directly and confidently based on the data above
2. The data has been PRE-FILTERED according to the user's requirements
3. If the user asked for a specific year, slot, theme, or any filter, the results ONLY include that criteria
4. Use the conversation context to understand pronouns and references
5. Present results clearly without adding disclaimers about data filtering or time periods
6. For counting/aggregation questions, provide the numbers and list the relevant items
7. Use natural language: "She (Huma Hina Nafees) has released most dramas on..." or "In 2024, the top 5 themes are..."
8. Only express uncertainty if there's genuinely NO relevant data in the results
9. Cite sources using [Source N] only when referencing specific document chunks
10. Be helpful, friendly, and confident - trust the query results

**CRITICAL - For Ranking/Top-N Queries:**
- If asked for "top N" or "highest" or "maximum", carefully scan ALL the data above
- Look through EVERY row/entry to find the actual highest values
- Don't just use the first few examples - examine the complete dataset
- Sort the results by the requested metric (GRP, rating, count, etc.) in descending order
- Verify you're providing the TRUE top N, not just the first N you encountered

**Your Answer:**"""

            # Generate response using LLM
            response = self.llm.invoke(prompt)

            # Extract content from response
            if hasattr(response, 'content'):
                answer = response.content
            else:
                answer = str(response)

            logger.info(f"Generated response of {len(answer)} characters")
            return answer

        except Exception as e:
            logger.error(f"Error generating LLM response: {e}")
            return f"I encountered an error generating a response: {str(e)}"

    def _map_reduce_query(
        self,
        query: str,
        chunks: List[Dict],
        conversation_history: List[Dict] = None
    ) -> str:
        """
        Map-Reduce pattern for handling large datasets that exceed token limits.

        This is the production-grade solution for queries on Excel/CSV data:
        1. Map Phase: Split chunks into batches, extract top N from each batch
        2. Reduce Phase: Combine batch results and get final top N

        Args:
            query: User's query (e.g., "top 5 dramas by GRPs")
            chunks: All retrieved chunks (could be 30-100+)
            conversation_history: Conversation context

        Returns:
            Final answer after map-reduce processing
        """
        logger.info(f"🗺️ Using Map-Reduce for large dataset query ({len(chunks)} chunks)")

        try:
            # Map Phase: Process chunks in batches
            batch_size = 10  # Each batch stays under token limit
            batch_results = []

            for i in range(0, len(chunks), batch_size):
                batch = chunks[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (len(chunks) + batch_size - 1) // batch_size

                logger.info(f"📊 Processing batch {batch_num}/{total_batches} ({len(batch)} chunks)")

                # Build context for this batch
                batch_context = "=== DATA BATCH ===\n\n"
                for idx, chunk in enumerate(batch, start=1):
                    content = chunk.get('content', '')
                    batch_context += f"[Chunk {idx}]\n{content}\n\n"

                # Ask LLM to extract top candidates from this batch
                map_prompt = f"""Extract the top candidates from this data batch.

**User's Question:** {query}

**Data Batch:**
{batch_context}

**Instructions:**
1. Identify the metric being asked for (GRP, revenue, count, rating, etc.)
2. Extract ALL items from this batch with their values
3. Return as JSON array with EXACT format: [{{"item": "name", "value": number}}, ...]
4. Include ALL items even if values are low - we'll filter later
5. CRITICAL: Return ONLY the JSON array, no other text

**Your JSON Response:**"""

                # Get batch results
                batch_response = self.llm.invoke(map_prompt)
                batch_text = batch_response.content if hasattr(batch_response, 'content') else str(batch_response)

                # Parse JSON (extract from markdown if needed)
                import json
                import re
                json_match = re.search(r'\[.*\]', batch_text, re.DOTALL)
                if json_match:
                    try:
                        batch_data = json.loads(json_match.group())
                        batch_results.extend(batch_data)
                        logger.info(f"✅ Extracted {len(batch_data)} items from batch {batch_num}")
                    except json.JSONDecodeError as e:
                        logger.warning(f"⚠️ Failed to parse JSON from batch {batch_num}: {e}")
                        # Continue with next batch
                        continue

            logger.info(f"📥 Map phase complete: {len(batch_results)} total candidates")

            # Reduce Phase: Combine and get final answer
            if not batch_results:
                return "I couldn't extract any data from the chunks. Please try rephrasing your query."

            # Sort and prepare combined results
            combined_json = json.dumps(batch_results, indent=2)

            reduce_prompt = f"""Based on the aggregated data from all batches, answer the user's question.

**User's Question:** {query}

**Aggregated Data from All Batches:**
{combined_json}

**Instructions:**
1. Sort the data by the requested metric in descending order
2. Extract the top N items as requested
3. Present the results clearly with names and values
4. Be confident - this data has been aggregated from the complete dataset

**Your Answer:**"""

            # Get final answer
            final_response = self.llm.invoke(reduce_prompt)
            final_answer = final_response.content if hasattr(final_response, 'content') else str(final_response)

            logger.info(f"✅ Reduce phase complete: Generated final answer ({len(final_answer)} chars)")
            return final_answer

        except Exception as e:
            logger.error(f"❌ Error in map-reduce query: {e}")
            return f"I encountered an error processing your query: {str(e)}"

    def _expand_query(self, query: str) -> List[str]:
        """
        Generate query variations using LLM paraphrasing.

        This increases retrieval coverage by generating semantic variations
        of the original query.

        Args:
            query: Original user query

        Returns:
            List of query variants: [original_query, paraphrase_1, paraphrase_2]
        """
        logger.debug(f"Expanding query: {query[:50]}...")

        try:
            expansion_prompt = f"""Generate 2 alternative phrasings of this question that preserve the intent but use different words:

Original: {query}

Alternatives (one per line):
"""

            response = self.llm.invoke(expansion_prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)

            # Parse alternatives
            alternatives = [line.strip().strip('12.-') for line in response_text.split('\n')
                          if line.strip() and not line.strip().startswith('Alternative')]

            # Return original + up to 2 alternatives
            result = [query] + alternatives[:2]
            logger.info(f"Expanded query to {len(result)} variants")
            return result

        except Exception as e:
            logger.warning(f"Query expansion failed: {e}. Using original query only.")
            return [query]

    def _rerank_results(self, query: str, chunks: List[Dict], top_k: int = 5) -> List[Dict]:
        """
        Rerank chunks using cross-encoder for better relevance scoring.

        Cross-encoders provide more accurate relevance scores than bi-encoder
        cosine similarity because they process query-chunk pairs directly.

        Args:
            query: Original query
            chunks: Retrieved chunks from vector search
            top_k: Number of top results to return

        Returns:
            List of reranked chunks with rerank_score added
        """
        if not self.reranker or not chunks:
            logger.warning("Reranker not available or no chunks to rerank")
            return chunks[:top_k]

        logger.debug(f"Reranking {len(chunks)} chunks")

        try:
            # Prepare query-chunk pairs
            pairs = [(query, chunk.get('content', '')) for chunk in chunks]

            # Score all pairs
            scores = self.reranker.predict(pairs)

            # Combine chunks with scores and sort
            ranked_chunks = []
            for chunk, score in zip(chunks, scores):
                chunk_copy = chunk.copy()
                chunk_copy['rerank_score'] = float(score)
                ranked_chunks.append(chunk_copy)

            # Sort by rerank score (descending)
            ranked_chunks.sort(key=lambda x: x['rerank_score'], reverse=True)

            logger.info(f"Reranked to top {min(top_k, len(ranked_chunks))} results")
            return ranked_chunks[:top_k]

        except Exception as e:
            logger.error(f"Reranking failed: {e}. Returning original order.")
            return chunks[:top_k]

    def _apply_mmr(self, query_emb: np.ndarray, chunks: List[Dict],
                   lambda_param: float = 0.7, top_k: int = 5) -> List[Dict]:
        """
        Apply Maximal Marginal Relevance for diversity in results.

        MMR = λ * relevance - (1-λ) * max_similarity_to_selected

        This prevents returning multiple nearly-identical chunks.

        Args:
            query_emb: Query embedding vector
            chunks: Candidate chunks (must have 'embedding' field)
            lambda_param: Balance between relevance (1.0) and diversity (0.0)
            top_k: Number of results to select

        Returns:
            List of diverse chunks
        """
        if not chunks or len(chunks) <= top_k:
            return chunks

        logger.debug(f"Applying MMR to {len(chunks)} chunks (lambda={lambda_param})")

        try:
            selected = []
            remaining = chunks.copy()

            # Extract embeddings - need to fetch if not present
            for chunk in remaining:
                if 'embedding' not in chunk:
                    # Generate embedding for this chunk
                    chunk['embedding'] = self.embedding_model.encode([chunk.get('content', '')])[ 0]

            while len(selected) < top_k and remaining:
                if not selected:
                    # First selection: pure relevance
                    similarities = []
                    for chunk in remaining:
                        sim = cosine_similarity([query_emb], [chunk['embedding']])[0][0]
                        similarities.append(sim)
                    best_idx = np.argmax(similarities)
                else:
                    # Subsequent selections: MMR
                    mmr_scores = []
                    selected_embs = np.array([chunk['embedding'] for chunk in selected])

                    for chunk in remaining:
                        chunk_emb = chunk['embedding']

                        # Relevance to query
                        relevance = cosine_similarity([query_emb], [chunk_emb])[0][0]

                        # Max similarity to already selected
                        similarities = cosine_similarity([chunk_emb], selected_embs)[0]
                        max_sim = np.max(similarities)

                        # MMR formula
                        mmr = lambda_param * relevance - (1 - lambda_param) * max_sim
                        mmr_scores.append(mmr)

                    best_idx = np.argmax(mmr_scores)

                # Move best from remaining to selected
                selected.append(remaining.pop(best_idx))

            logger.info(f"MMR selected {len(selected)} diverse results")
            return selected

        except Exception as e:
            logger.error(f"MMR failed: {e}. Returning top_k chunks.")
            return chunks[:top_k]

    def _format_sources(self, chunks: List[Dict]) -> List[Dict]:
        """
        Format chunk sources for frontend display.

        Args:
            chunks: Retrieved chunks

        Returns:
            List of formatted source dicts (JSON-serializable)
        """
        sources = []

        for idx, chunk in enumerate(chunks, start=1):
            content = str(chunk.get('content', ''))
            preview = content[:200] + "..." if len(content) > 200 else content

            source = {
                'number': int(idx),
                'content': preview,
                'similarity': float(round(chunk.get('similarity', 0), 3)),
                'document_id': str(chunk.get('document_id', '')),
                'metadata': dict(chunk.get('chunk_metadata', {}))
            }
            sources.append(source)

        return sources

    def classify_query_type(self, query: str, confidence_threshold: float = 0.6) -> Dict[str, Any]:
        """
        Semantically classify query type using embedding similarity to exemplars.

        This is more accurate than keyword matching as it understands semantic intent.

        Types:
        - 'rag': Pure document Q&A
        - 'sql': Structured data query
        - 'prediction': Predictive analytics
        - 'hybrid': Combination of multiple types

        Args:
            query: User's query
            confidence_threshold: Minimum similarity score to confidently classify

        Returns:
            Dict with 'type' (str), 'confidence' (float), and 'scores' (dict)
        """
        logger.debug(f"Classifying query type: {query[:50]}...")

        # Define exemplar queries for each category
        exemplars = {
            'rag': [
                "What does document X say about topic Y?",
                "Summarize the key points from the report",
                "What are the main findings in the research paper?",
                "Explain the methodology described in the document",
                "What recommendations are mentioned in the proposal?"
            ],
            'sql': [
                "What is the average value in column X?",
                "How many rows have status completed?",
                "Calculate the total sales by region",
                "Show me the top 10 customers by revenue",
                "Filter the data where amount is greater than 1000"
            ],
            'prediction': [
                "Forecast sales for next quarter",
                "What will the trend be in 6 months?",
                "Predict the peak demand period",
                "What is the probability of exceeding the target?",
                "Project the growth rate for next year"
            ]
        }

        try:
            # Encode query
            query_emb = self.embedding_model.encode([query])[0]

            # Calculate average similarity to exemplars for each category
            category_scores = {}

            for category, category_exemplars in exemplars.items():
                exemplar_embs = self.embedding_model.encode(category_exemplars)
                similarities = cosine_similarity([query_emb], exemplar_embs)[0]
                avg_similarity = float(np.mean(similarities))
                max_similarity = float(np.max(similarities))

                # Use weighted combination: 70% max, 30% avg
                category_scores[category] = 0.7 * max_similarity + 0.3 * avg_similarity

            logger.debug(f"Category scores: {category_scores}")

            # Find best matching category
            best_category = max(category_scores.items(), key=lambda x: x[1])
            category_type = best_category[0]
            confidence = best_category[1]

            # Check if multiple categories have high scores (hybrid query)
            high_score_categories = [cat for cat, score in category_scores.items()
                                    if score >= confidence_threshold]

            if len(high_score_categories) > 1:
                category_type = 'hybrid'
                logger.info(f"Query classified as hybrid (multiple high scores): {high_score_categories}")
            elif confidence < confidence_threshold:
                # Low confidence - default to RAG
                category_type = 'rag'
                logger.info(f"Low confidence ({confidence:.2f}), defaulting to RAG")
            else:
                logger.info(f"Query classified as {category_type} (confidence: {confidence:.2f})")

            return {
                'type': category_type,
                'confidence': confidence,
                'scores': category_scores
            }

        except Exception as e:
            logger.error(f"Error in semantic query classification: {e}. Defaulting to RAG.")
            return {
                'type': 'rag',
                'confidence': 0.0,
                'scores': {},
                'error': str(e)
            }

    def should_generate_visualization(self, query: str, sql_results: str) -> Dict[str, Any]:
        """
        Detect if query needs visualization based on:
        - Explicit requests ("chart", "plot", "graph", "visualize")
        - Statistical queries ("count", "average", "sum", "trend")
        - Comparison queries ("compare", "versus", "top N")
        - SQL results with numeric data

        Args:
            query: User's natural language query
            sql_results: SQL query results string

        Returns:
            {
                'should_visualize': bool,
                'visualization_type': str,  # 'explicit' or 'automatic'
                'suggested_chart': str,      # 'bar', 'line', 'pie', 'auto'
                'sql_data': str              # SQL results for chart generation
            }
        """
        logger.info(f"Checking if visualization needed for query: {query}")

        try:
            # If no SQL results, no visualization
            if not sql_results or len(sql_results.strip()) < 10:
                logger.debug("No SQL results, skipping visualization")
                return {'should_visualize': False}

            query_lower = query.lower()

            # Check for explicit visualization requests
            explicit_keywords = ['chart', 'plot', 'graph', 'visualize', 'visualization',
                                'show me', 'display', 'draw', 'create a', 'generate a']

            is_explicit = any(keyword in query_lower for keyword in explicit_keywords)

            # Check for statistical/aggregation queries (good candidates for charts)
            statistical_keywords = ['count', 'average', 'sum', 'total', 'mean',
                                   'trend', 'over time', 'by year', 'by month',
                                   'by channel', 'by category', 'distribution']

            is_statistical = any(keyword in query_lower for keyword in statistical_keywords)

            # Check for comparison queries
            comparison_keywords = ['compare', 'versus', 'vs', 'top', 'bottom',
                                  'most', 'least', 'highest', 'lowest', 'rank',
                                  'best', 'worst', 'which', 'how many']

            is_comparison = any(keyword in query_lower for keyword in comparison_keywords)

            # Determine if should visualize
            should_viz = is_explicit or is_statistical or is_comparison

            if not should_viz:
                logger.debug("Query doesn't match visualization patterns")
                return {'should_visualize': False}

            # Determine suggested chart type
            suggested_chart = 'auto'

            if 'pie' in query_lower or 'proportion' in query_lower or 'percentage' in query_lower:
                suggested_chart = 'pie'
            elif 'line' in query_lower or 'trend' in query_lower or 'over time' in query_lower:
                suggested_chart = 'line'
            elif 'bar' in query_lower or 'compare' in query_lower or 'count' in query_lower:
                suggested_chart = 'bar'
            elif 'scatter' in query_lower or 'relationship' in query_lower:
                suggested_chart = 'scatter'

            visualization_type = 'explicit' if is_explicit else 'automatic'

            logger.info(f"Visualization needed: {visualization_type}, suggested: {suggested_chart}")

            return {
                'should_visualize': True,
                'visualization_type': visualization_type,
                'suggested_chart': suggested_chart,
                'sql_data': sql_results,
                'query': query
            }

        except Exception as e:
            logger.error(f"Error in visualization detection: {e}")
            return {'should_visualize': False}


class QueryRouter:
    """
    Route queries to appropriate handlers based on query type.

    This class determines whether a query should be handled by:
    - RAG engine (document Q&A)
    - SQL agent (structured data queries)
    - Predictive analyzer (forecasting, analytics)
    - Hybrid approach (combination)
    """

    def __init__(self, rag_engine: KnowledgeBaseRAG):
        self.rag_engine = rag_engine
        logger.info("QueryRouter initialized")

    def route_query(self, kb_id: str, query: str) -> Dict:
        """
        Route query to appropriate handler using semantic classification.

        Args:
            kb_id: Knowledge base ID
            query: User query

        Returns:
            Dict with query_type, confidence, scores, and routing decisions
        """
        classification = self.rag_engine.classify_query_type(query)
        query_type = classification['type']
        logger.info(f"Query classified as: {query_type} (confidence: {classification.get('confidence', 0):.2f})")

        return {
            'query_type': query_type,
            'confidence': classification.get('confidence', 0),
            'scores': classification.get('scores', {}),
            'should_use_rag': query_type in ['rag', 'hybrid'],
            'should_use_sql': query_type in ['sql', 'hybrid'],
            'should_use_prediction': query_type in ['prediction', 'hybrid']
        }


# Utility functions for integration

def get_kb_rag_engine(llm, supabase_client, embedding_model: str = 'sentence-transformers/all-MiniLM-L6-v2'):
    """
    Factory function to create KnowledgeBaseRAG instance.

    Args:
        llm: LangChain LLM instance
        supabase_client: Supabase client
        embedding_model: Embedding model name

    Returns:
        KnowledgeBaseRAG instance
    """
    return KnowledgeBaseRAG(llm, embedding_model, supabase_client)


# Example usage
if __name__ == "__main__":
    # Setup logging for testing
    logging.basicConfig(level=logging.INFO)

    print("KnowledgeBaseRAG module loaded successfully")
    print("Ready for integration with backend/main.py")
