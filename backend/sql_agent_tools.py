"""
Custom SQL exploration tools for intelligent column selection.

This module provides specialized LangChain tools that enable the SQL agent
to explore column contents when faced with ambiguous column selection decisions.

Author: EDI.ai Team
Date: 2026-01-10
"""

import logging
from typing import Any, Type
from langchain_core.tools import BaseTool
from langchain_community.utilities.sql_database import SQLDatabase
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DistinctValuesInput(BaseModel):
    """Input schema for sql_db_distinct_values tool."""
    table_name: str = Field(description="Name of the table to query")
    column_name: str = Field(description="Name of the column to analyze")
    limit: int = Field(default=10, description="Number of top distinct values to return")


class SQLDistinctValuesTool(BaseTool):
    """
    Tool to get distinct values and their counts from a column.

    Use this tool when:
    - Column names are ambiguous (e.g., Genre vs Theme, Title vs Name)
    - You need to see actual values before deciding which column to query
    - Schema doesn't make column purpose clear
    - Multiple columns have similar names or purposes

    Returns top N distinct values with their occurrence counts.

    Example usage:
    - User asks: "show me crime dramas"
    - Agent sees: Genre (1 distinct), Theme (42 distinct)
    - Agent calls: sql_db_distinct_values(table="kb_data_table", column="Theme", limit=10)
    - Tool returns: Theme values like "Crime/Thriller", "Romance", "Drama", etc.
    - Agent decides: Use Theme column for filtering
    """

    name: str = "sql_db_distinct_values"
    description: str = """
Get distinct values and their counts for a specific column in a table.

Use this when:
- Column names are ambiguous (e.g., Genre vs Theme, Title vs Name, Category vs Type)
- You need to see actual values before deciding which column to query
- The schema shows multiple columns with similar purposes
- You're unsure if a column contains the data you're looking for

Input:
- table_name: Name of the table to query
- column_name: Name of the column to analyze
- limit: Number of top distinct values to return (default: 10)

Returns:
- Total distinct count
- Top N values with occurrence counts
- Helps you decide if this column contains the right data for the query

Example:
sql_db_distinct_values(table_name="kb_data_table", column_name="Theme", limit=10)
"""
    args_schema: Type[BaseModel] = DistinctValuesInput
    db: SQLDatabase

    def _run(
        self,
        table_name: str,
        column_name: str,
        limit: int = 10
    ) -> str:
        """
        Execute the tool to get distinct values from a column.

        Args:
            table_name: Name of the table
            column_name: Name of the column to analyze
            limit: Number of top values to return

        Returns:
            Formatted string with distinct count and top values
        """
        try:
            logger.info(f"🔍 Exploring column: {column_name} in table: {table_name}")

            # Get total distinct count
            count_query = f'SELECT COUNT(DISTINCT "{column_name}") FROM "{table_name}"'
            distinct_count = self.db.run_no_throw(count_query).strip()

            logger.info(f"Found {distinct_count} distinct values")

            # Get top values with counts
            values_query = f'''
SELECT "{column_name}", COUNT(*) as count
FROM "{table_name}"
WHERE "{column_name}" IS NOT NULL
GROUP BY "{column_name}"
ORDER BY count DESC
LIMIT {limit}
'''
            result = self.db.run_no_throw(values_query)

            # Format response
            response = f'Column "{column_name}" has {distinct_count} distinct values.\n\n'
            response += f'Top {limit} values with counts:\n{result}\n\n'
            response += 'Use this information to decide if this column contains the data you need for the query.'

            logger.info(f"✅ Successfully explored column {column_name}")
            return response

        except Exception as e:
            error_msg = f"Error analyzing column '{column_name}': {str(e)}"
            logger.error(f"❌ {error_msg}")
            return error_msg

    async def _arun(
        self,
        table_name: str,
        column_name: str,
        limit: int = 10
    ) -> str:
        """Async implementation - not supported, falls back to sync."""
        return self._run(table_name, column_name, limit)


def create_sql_exploration_tools(db: SQLDatabase) -> list:
    """
    Factory function to create all SQL exploration tools.

    Args:
        db: SQLDatabase instance to use for queries

    Returns:
        List of exploration tool instances
    """
    return [
        SQLDistinctValuesTool(db=db)
    ]
