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
from typing import Dict, List, Optional, Any
import numpy as np  # Keep for type hints in old RAG methods
from sqlalchemy import create_engine, text
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit, create_sql_agent
from langchain.agents import AgentType

# Note: Vector search imports removed (sentence_transformers, sklearn, qdrant_manager)
# SQL agent mode only - numpy kept for type hints only

# Setup logging
logger = logging.getLogger(__name__)

# SQL Agent Timeout Configurations
TIMEOUT_CONFIGS = {
    'simple': {
        'max_iterations': 15,
        'max_execution_time': 90,  # 1.5 minutes
    },
    'moderate': {
        'max_iterations': 25,
        'max_execution_time': 150,  # 2.5 minutes
    },
    'complex': {
        'max_iterations': 35,
        'max_execution_time': 240,  # 4 minutes
    }
}

# Retry Configuration
RETRY_CONFIG = {
    'max_retries': 3,
    'backoff_multiplier': 2,  # 2s, 4s, 8s
}


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

    def _classify_error_type(self, error: Exception) -> Dict[str, Any]:
        """
        Classify error to determine retry strategy.

        Returns dict with:
        - error_type: 'timeout' | 'parsing' | 'database' | 'rate_limit' | 'other'
        - should_retry: bool
        - wait_seconds: int (for backoff)
        - user_message: str
        """
        error_str = str(error).lower()

        # Timeout errors
        if any(pattern in error_str for pattern in [
            'iteration limit', 'time limit', 'timed out', 'timeout'
        ]):
            return {
                'error_type': 'timeout',
                'should_retry': True,
                'wait_seconds': 0,
                'user_message': 'Query taking longer than expected, retrying with extended timeout...'
            }

        # Parsing errors
        if any(pattern in error_str for pattern in [
            'could not parse', 'parsing error', 'invalid format'
        ]):
            return {
                'error_type': 'parsing',
                'should_retry': True,
                'wait_seconds': 2,
                'user_message': 'Reformatting query, please wait...'
            }

        # Rate limit errors
        if any(pattern in error_str for pattern in [
            'rate limit', '429', 'too many requests'
        ]):
            return {
                'error_type': 'rate_limit',
                'should_retry': True,
                'wait_seconds': 10,
                'user_message': 'API rate limit reached, waiting before retry...'
            }

        # Database errors (don't retry)
        if any(pattern in error_str for pattern in [
            'syntax error', 'does not exist', 'permission denied'
        ]):
            return {
                'error_type': 'database',
                'should_retry': False,
                'wait_seconds': 0,
                'user_message': 'Database query error'
            }

        # Other errors
        return {
            'error_type': 'other',
            'should_retry': True,
            'wait_seconds': 2,
            'user_message': 'Unexpected error, retrying...'
        }

    def _classify_query_complexity(self, query: str) -> str:
        """
        Analyze query to determine timeout configuration.

        Returns: 'simple' | 'moderate' | 'complex'
        """
        complexity_score = 0
        query_upper = query.upper()

        # Indicators of complexity
        if 'JOIN' in query_upper:
            complexity_score += 2
        if 'GROUP BY' in query_upper:
            complexity_score += 1
        if 'HAVING' in query_upper:
            complexity_score += 2
        if query_upper.count('SELECT') > 1:  # Subqueries
            complexity_score += 3
        if any(word in query for word in ['last', 'previous', 'year', 'month']):
            complexity_score += 1  # Temporal queries need more reasoning

        # Classify
        if complexity_score <= 2:
            return 'simple'
        elif complexity_score <= 5:
            return 'moderate'
        else:
            return 'complex'

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
                    'response': 'No documents found in this knowledge base. Please upload a file first.',
                    'sources': []
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
                    'response': 'No queryable data found in this knowledge base.',
                    'sources': []
                }

            logger.info(f"📊 Found {len(tables_info)} table(s) in KB")

            # Step 3: Create SQL agent with ALL tables
            all_table_names = [t['table_name'] for t in tables_info]
            logger.info(f"📊 Creating SQL agent with {len(all_table_names)} table(s): {', '.join(all_table_names)}")

            # Get Postgres connection from environment
            db_url = os.getenv('SUPABASE_DB_URL')
            if not db_url:
                return {
                    'error': 'SUPABASE_DB_URL not configured',
                    'response': 'Database connection not configured. Please check server settings.',
                    'sources': []
                }

            engine = create_engine(db_url)
            db = SQLDatabase(engine, include_tables=all_table_names)  # Pass ALL tables
            toolkit = SQLDatabaseToolkit(db=db, llm=self.llm)

            # Step 4: Build system message with info about ALL tables
            table_descriptions = []
            for table_info in tables_info:
                cols = ', '.join(table_info['columns'])
                table_descriptions.append(
                    f"- **{table_info['table_name']}** (from {table_info['filename']})\n"
                    f"  Columns: {cols}\n"
                    f"  Rows: {table_info['row_count']}"
                )

            tables_desc = '\n'.join(table_descriptions)

            # PART B: Preprocess query to add date hints
            enhanced_query = self._enhance_time_based_query(query)
            logger.info(f"Enhanced query: {enhanced_query}")

            # Format conversation context for pronoun resolution
            conversation_context = self._format_conversation_context(conversation_history)

            # PART A: Format temporal context for system prompt
            temporal_context = self._format_temporal_context(tables_info)

            system_message = f"""You are a SQL expert assistant analyzing structured data.

**Available Tables in Database:**
{tables_desc}
{conversation_context}
{temporal_context}

**CRITICAL INSTRUCTIONS:**
1. You have access to {len(tables_info)} table(s) - analyze the question to determine which to use
2. Column names may contain spaces - use double quotes: "Column Name"
3. Table names are already lowercase - use them as-is
4. For "top N" queries: ORDER BY [metric] DESC LIMIT N
5. For "bottom N" queries: ORDER BY [metric] ASC LIMIT N
6. You can JOIN tables if the question requires data from multiple files
7. Be precise - return exact numbers, not approximations
8. Provide clear, complete answers with data
9. **Resolve pronouns and references using conversation context above**
10. **FORMAT NUMBERS AS WHOLE INTEGERS - do not include decimal places in your responses**
    Example: Say "GRPS is 3159" NOT "GRPS is 3159.682"

**Pronoun Resolution Examples:**
- Previous: "Huma Nafees has highest GRPs"
  Current: "which channel has she released dramas on"
  → Resolve "she" = "Huma Nafees", query: SELECT "Channel", COUNT(*) ... WHERE "Writer" LIKE '%Huma Nafees%'

- Previous: "Top 5 dramas: Kabhi Main Kabhi Tum, Nand, Baylagaam, Fitrat, Behroop"
  Current: "what are their GRPs"
  → Resolve "their" = those 5 dramas, query: SELECT "Drama", "GRPS" ... WHERE "Drama" IN (...)

- Previous: "ARY channel has the best dramas"
  Current: "show me their top dramas"
  → Resolve "their" = ARY, query: SELECT * ... WHERE "Channel" = 'ARY-D'

**Your task:** Answer the user's question using SQL queries on the available tables.
"""

            # Define custom error handler for parsing errors
            def handle_parsing_error(error) -> str:
                """Handle parsing errors by returning a helpful message to the agent."""
                return (
                    "I encountered a formatting error. Let me provide the final answer.\n"
                    "I should respond with 'Final Answer:' followed by the complete answer to the user's question."
                )

            # Step 4: Check if visualization is requested
            viz_info = self._should_generate_visualization(query)

            # BRANCH: If visualization requested, skip SQL agent and go directly to visualization
            if viz_info['should_visualize']:
                logger.info(f"📊 Visualization requested - skipping SQL agent, generating viz directly")
                return self._generate_visualization_directly(
                    query=enhanced_query,
                    kb_id=kb_id,
                    tables_info=tables_info,
                    db_url=db_url,
                    suggested_chart=viz_info['suggested_chart'],
                    conversation_history=conversation_history
                )

            # BRANCH: No visualization - use SQL agent with retry logic
            logger.info(f"🔄 Executing SQL agent with retry logic...")

            # Classify query complexity
            complexity = self._classify_query_complexity(enhanced_query)
            logger.info(f"Query complexity: {complexity}")

            # Initialize variables for retry loop
            answer = ""
            intermediate_steps = []
            sql_queries = []
            agent_error = None
            attempt = 0
            max_retries = RETRY_CONFIG['max_retries']

            # Try with progressive retry
            while attempt < max_retries:
                try:
                    # Select timeout config based on attempt
                    if attempt == 0:
                        config = TIMEOUT_CONFIGS[complexity]
                    else:
                        # Use more relaxed config for retries
                        config = TIMEOUT_CONFIGS['complex']

                    logger.info(f"Attempt {attempt + 1}/{max_retries} with config: max_iterations={config['max_iterations']}, max_execution_time={config['max_execution_time']}s")

                    # Create SQL agent with current config
                    sql_agent = create_sql_agent(
                        llm=self.llm,
                        toolkit=toolkit,
                        agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
                        verbose=True,
                        handle_parsing_errors=handle_parsing_error,
                        max_iterations=config['max_iterations'],
                        max_execution_time=config['max_execution_time'],
                        agent_kwargs={
                            "system_message": system_message,
                            "prefix": f"Answer the question about data in the available table(s)."
                        }
                    )

                    # Execute agent
                    result = sql_agent.invoke({"input": enhanced_query})
                    answer = result.get("output", "")
                    answer = self._remove_decimals_from_response(answer)
                    intermediate_steps = result.get("intermediate_steps", [])

                    # Extract SQL queries from intermediate steps
                    for step in intermediate_steps:
                        if isinstance(step, tuple) and len(step) > 0:
                            action = step[0]
                            if hasattr(action, 'tool_input'):
                                sql_queries.append(action.tool_input)

                    logger.info(f"✅ SQL agent succeeded on attempt {attempt + 1}. Generated {len(sql_queries)} queries")
                    break  # Success! Exit retry loop

                except Exception as e:
                    agent_error = str(e)
                    logger.error(f"❌ SQL agent error on attempt {attempt + 1}: {agent_error}")

                    # Classify error
                    error_info = self._classify_error_type(e)
                    logger.info(f"Error classified as: {error_info['error_type']}")

                    # Check if should retry
                    if not error_info['should_retry'] or attempt == max_retries - 1:
                        logger.error(f"Not retrying. Error type: {error_info['error_type']}")
                        break

                    # Wait before retry (exponential backoff)
                    wait_time = error_info['wait_seconds'] + (RETRY_CONFIG['backoff_multiplier'] ** attempt)
                    logger.info(f"Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)

                    attempt += 1

            # If all retries failed
            if agent_error and attempt == max_retries:
                logger.error(f"❌ All {max_retries} attempts failed")
                return {
                    'error': agent_error,
                    'response': f"I encountered an error after {max_retries} attempts: {agent_error}\n\nThis query may be too complex. Try simplifying your question or breaking it into smaller parts.",
                    'sources': [],
                    'method': 'sql_agent_failed',
                    'tables_queried': [table_info['filename'] for table_info in tables_info],
                    'num_sources': 0
                }

            # Track which tables were actually queried
            tables_used = []
            for sql_query in sql_queries:
                for table_info in tables_info:
                    if table_info['table_name'] in sql_query.lower():
                        if table_info['filename'] not in tables_used:
                            tables_used.append(table_info['filename'])

            logger.info(f"📊 Tables queried: {', '.join(tables_used) if tables_used else 'none detected'}")

            # Build response (no visualization in SQL agent branch)
            response_dict = {
                'response': answer,
                'sources': [],  # No sources displayed to user
                'method': 'sql_agent',
                'sql_queries': sql_queries,  # Keep for debugging
                'tables_queried': tables_used,  # Track which files were used
                'num_sources': len(tables_used)
            }

            return response_dict

        except Exception as e:
            logger.error(f"❌ Unexpected error in query_kb: {e}")
            import traceback
            traceback.print_exc()
            return {
                'error': str(e),
                'response': f"I encountered an error: {str(e)}",
                'sources': []
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
                    'response': 'No data tables found in this knowledge base.',
                    'sources': []
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
    print(f"Error: {{str(e)}}")
    result = f"Error: {{str(e)}}"
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
                    'response': "I couldn't generate the visualization.",
                    'sources': []
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
                'sources': [],
                'method': 'direct_visualization',
                'tables_queried': [table_info['filename']],
                'num_sources': 1,
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
                'response': f"I encountered an error generating the visualization: {str(e)}",
                'sources': []
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
