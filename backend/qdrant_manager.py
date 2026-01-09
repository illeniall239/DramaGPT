"""
Qdrant Vector Database Manager

Handles all vector operations with Qdrant Cloud for high-performance similarity search.

Author: EDI.ai Team
Date: 2026-01-04
"""

import os
import logging
import uuid
from typing import List, Dict, Optional
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    SearchRequest,
    PayloadSchemaType
)
from dotenv import load_dotenv

# Setup logging
logger = logging.getLogger(__name__)


class QdrantManager:
    """
    Manages vector storage and retrieval using Qdrant Cloud.

    Features:
    - High-performance vector similarity search
    - Advanced metadata filtering
    - Automatic collection creation
    - Batch operations for efficiency
    - Hybrid search capabilities
    """

    def __init__(self):
        """Initialize Qdrant client with credentials from environment."""
        load_dotenv()

        self.url = os.getenv('QDRANT_URL')
        self.api_key = os.getenv('QDRANT_API_KEY')
        self.collection_name = os.getenv('QDRANT_COLLECTION', 'kb_vectors')

        if not self.url:
            raise ValueError("QDRANT_URL not found in environment variables")
        if not self.api_key or self.api_key == 'your_qdrant_api_key_here':
            raise ValueError(
                "QDRANT_API_KEY not configured. "
                "Please add your Qdrant API key to .env file"
            )

        # Initialize client
        try:
            self.client = QdrantClient(
                url=self.url,
                api_key=self.api_key,
                timeout=30
            )
            logger.info(f"✅ Connected to Qdrant at {self.url}")

            # Ensure collection exists
            self._ensure_collection()

        except Exception as e:
            logger.error(f"❌ Failed to connect to Qdrant: {e}")
            raise

    def _ensure_collection(self):
        """Create collection with proper indexes if it doesn't exist."""
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]

            # If collection already exists, just return (don't delete it!)
            if self.collection_name in collection_names:
                logger.info(f"✅ Collection exists: {self.collection_name}")
                return

            # Collection doesn't exist - create it with indexes
            logger.info(f"Creating Qdrant collection: {self.collection_name}")

            # Create collection
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=384,  # sentence-transformers/all-MiniLM-L6-v2 dimension
                    distance=Distance.COSINE
                )
            )
            logger.info(f"✅ Created collection: {self.collection_name}")

            # Create payload index for kb_id to enable filtering
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="kb_id",
                field_schema=PayloadSchemaType.KEYWORD
            )
            logger.info(f"✅ Created payload index for kb_id field")

        except Exception as e:
            logger.error(f"❌ Error ensuring collection: {e}")
            raise

    def store_vectors(
        self,
        kb_id: str,
        document_id: str,
        chunks: List[str],
        embeddings: np.ndarray,
        metadata_list: List[Dict]
    ) -> bool:
        """
        Store document chunks and embeddings in Qdrant.

        Args:
            kb_id: Knowledge base ID
            document_id: Document ID (from Supabase)
            chunks: List of text chunks
            embeddings: NumPy array of embeddings (n_chunks, 384)
            metadata_list: List of metadata dicts (one per chunk)

        Returns:
            True if successful
        """
        logger.info(f"📤 Storing {len(chunks)} vectors in Qdrant for doc {document_id}")

        try:
            points = []

            for idx, (chunk, embedding, metadata) in enumerate(zip(chunks, embeddings, metadata_list)):
                # Create unique point ID as UUID (Qdrant requirement)
                # Generate deterministic UUID from document_id + chunk_index
                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{document_id}_{idx}"))

                # Prepare payload (metadata)
                payload = {
                    'kb_id': kb_id,
                    'document_id': document_id,
                    'chunk_index': idx,
                    'content': chunk,
                    **metadata  # Add all metadata fields
                }

                # Create point
                point = PointStruct(
                    id=point_id,
                    vector=embedding.tolist(),
                    payload=payload
                )
                points.append(point)

            # Batch upload
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )

            logger.info(f"✅ Stored {len(points)} vectors in Qdrant")
            return True

        except Exception as e:
            logger.error(f"❌ Error storing vectors in Qdrant: {e}")
            raise

    def search_similar(
        self,
        kb_id: str,
        query_embedding: np.ndarray,
        top_k: int = 10,
        filters: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Search for similar vectors in Qdrant.

        Args:
            kb_id: Knowledge base ID to search within
            query_embedding: Query vector (384-dimensional)
            top_k: Number of results to return
            filters: Optional metadata filters

        Returns:
            List of dicts with id, score, content, metadata
        """
        logger.debug(f"🔍 Searching Qdrant for top {top_k} results in KB {kb_id}")

        try:
            # Build filter for KB ID
            filter_conditions = [
                FieldCondition(
                    key="kb_id",
                    match=MatchValue(value=kb_id)
                )
            ]

            # Add additional filters if provided
            if filters:
                for key, value in filters.items():
                    filter_conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=value)
                        )
                    )

            search_filter = Filter(must=filter_conditions) if filter_conditions else None

            # Search using correct Qdrant API method
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_embedding.tolist(),  # Changed: query_vector → query
                query_filter=search_filter,
                limit=top_k,
                with_payload=True
            )

            # Extract points from response
            results = response.points

            # Format results
            formatted_results = []
            for result in results:
                formatted_results.append({
                    'id': result.id,
                    'score': float(result.score),
                    'content': result.payload.get('content', ''),
                    'document_id': result.payload.get('document_id'),
                    'chunk_index': result.payload.get('chunk_index'),
                    'metadata': {k: v for k, v in result.payload.items()
                                if k not in ['content', 'document_id', 'chunk_index', 'kb_id']}
                })

            logger.info(f"✅ Found {len(formatted_results)} results from Qdrant")
            return formatted_results

        except Exception as e:
            logger.error(f"❌ Error searching Qdrant: {e}")
            raise

    def delete_document_vectors(self, document_id: str) -> bool:
        """
        Delete all vectors for a specific document.

        Args:
            document_id: Document ID

        Returns:
            True if successful
        """
        logger.info(f"🗑️ Deleting vectors for document {document_id}")

        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="document_id",
                            match=MatchValue(value=document_id)
                        )
                    ]
                )
            )

            logger.info(f"✅ Deleted vectors for document {document_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Error deleting vectors: {e}")
            raise

    def delete_kb_vectors(self, kb_id: str) -> bool:
        """
        Delete all vectors for a knowledge base.

        Args:
            kb_id: Knowledge base ID

        Returns:
            True if successful
        """
        logger.info(f"🗑️ Deleting all vectors for KB {kb_id}")

        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="kb_id",
                            match=MatchValue(value=kb_id)
                        )
                    ]
                )
            )

            logger.info(f"✅ Deleted all vectors for KB {kb_id}")
            return True

        except Exception as e:
            logger.error(f"❌ Error deleting KB vectors: {e}")
            raise

    def get_collection_info(self) -> Dict:
        """Get information about the collection."""
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                'name': info.config.params.vectors.size,
                'vectors_count': info.vectors_count,
                'points_count': info.points_count,
                'status': info.status
            }
        except Exception as e:
            logger.error(f"❌ Error getting collection info: {e}")
            return {}


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Initialize manager
    manager = QdrantManager()

    # Get collection info
    info = manager.get_collection_info()
    print(f"Collection info: {info}")
