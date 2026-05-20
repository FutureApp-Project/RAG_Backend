# app/services/vector_store_service.py:

import sqlite3
import chromadb

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader
from langchain_ollama import OllamaEmbeddings
import os
import chromadb.errors
from typing import List, Dict, Any, Optional
from app.config.log.log_config import get_logger
import hashlib
from cachetools import TTLCache
import threading

logger = get_logger("vector_store_service")


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def ensure_chromadb_schema(persist_directory):
    db_path = os.path.join(persist_directory, "chroma.sqlite3")
    if not os.path.exists(db_path):
        # Let ChromaDB initialize it on first use
        return
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='collections';"
        )
        if not cursor.fetchone():
            logger.error(
                "ChromaDB schema missing 'collections' table. Please reinitialize the database or check ChromaDB setup."
            )
        conn.close()
    except Exception as e:
        logger.error(f"Error checking ChromaDB schema: {e}")


# Configurable thresholds
SIMILARITY_THRESHOLD_DIRECT = float(os.getenv("SIMILARITY_THRESHOLD_DIRECT", "0.85"))
SIMILARITY_THRESHOLD_RELEVANT = float(os.getenv("SIMILARITY_THRESHOLD_RELEVANT", "0.3"))
QR_COLLECTION_NAME = "query_response_pairs"
DOC_COLLECTION_NAME = "medical_documents"


class VectorStoreService:
    def __init__(self, persist_directory: str = "./chromadb"):
        self.persist_directory = persist_directory
        cache_maxsize = int(os.getenv("RESPONSE_CACHE_SIZE", "500"))
        cache_ttl = int(os.getenv("RESPONSE_CACHE_TTL", "3600"))
        self._response_cache = TTLCache(maxsize=cache_maxsize, ttl=cache_ttl)
        self._cache_lock = threading.Lock()
        self.available = False
        self.initialization_error: Optional[str] = None
        self.client = None
        self.embedding_model = None
        self.text_splitter = None

        try:
            os.makedirs(persist_directory, exist_ok=True)
            ensure_chromadb_schema(persist_directory)

            # Initialize ChromaDB client with persistent storage
            self.client = chromadb.PersistentClient(path=persist_directory)

            # Get Ollama settings from environment
            ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            ollama_model = _get_required_env("EMBEDDING_MODEL")

            # Initialize Ollama embedding model
            self.embedding_model = OllamaEmbeddings(
                base_url=ollama_base_url, model=ollama_model
            )

            # Initialize text splitter
            self.text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=500,
                chunk_overlap=50,
                length_function=len,
                separators=["\n\n", "\n", ". ", " ", ""],
            )

            # Ensure query-response collection exists
            self._ensure_qr_collection()
            self.available = True

            logger.info(
                f"VectorStoreService initialized with Ollama model: {ollama_model}"
            )
            logger.info(f"Ollama base URL: {ollama_base_url}")
            logger.info(
                f"Thresholds: direct={SIMILARITY_THRESHOLD_DIRECT}, relevant={SIMILARITY_THRESHOLD_RELEVANT}"
            )
            logger.info(
                f"VectorStoreService initialized with directory: {persist_directory}"
            )
        except Exception as e:
            self.initialization_error = str(e)
            logger.exception("VectorStoreService initialization failed: %s", str(e))

    def _is_available(self, operation: str) -> bool:
        if self.available:
            return True
        logger.warning(
            "Vector store unavailable during %s: %s",
            operation,
            self.initialization_error or "unknown error",
        )
        return False

    def _ensure_qr_collection(self):
        """Ensure the query-response pair collection exists"""
        if not self.client:
            return
        try:
            self.client.get_collection(name=QR_COLLECTION_NAME)
        except Exception:
            self.client.create_collection(
                name=QR_COLLECTION_NAME,
                metadata={
                    "description": "Cached query-response pairs for fast retrieval"
                },
            )
            logger.info(f"Created collection '{QR_COLLECTION_NAME}'")

    def create_collection(self, collection_name: str = "medical_documents"):
        """Create or get a collection - FIXED VERSION"""
        if not self._is_available("create_collection") or not self.client:
            raise RuntimeError(
                f"Vector store unavailable: {self.initialization_error or 'initialization failed'}"
            )
        try:
            # Try to get existing collection
            try:
                collection = self.client.get_collection(name=collection_name)
                count = collection.count()
                # REMOVE Unicode checkmark to avoid encoding error
                logger.info(
                    f"Collection '{collection_name}' exists with {count} documents"
                )
                return collection
            except Exception as e:
                # Check if it's a "not found" error
                error_str = str(e).lower()
                if "not found" in error_str or "does not exist" in error_str:
                    # Collection doesn't exist, create it
                    collection = self.client.create_collection(
                        name=collection_name,
                        metadata={"description": "Medical documents collection"},
                    )
                    logger.info(f"Created new collection '{collection_name}'")
                    return collection
                else:
                    # Some other error, re-raise it
                    raise e

        except Exception as e:
            # REMOVE Unicode X symbol
            logger.error(f"Error with collection '{collection_name}': {str(e)}")
            raise

    def upload_pdf(
        self, pdf_path: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Upload and process PDF file, converting to vectors"""
        if not self._is_available("upload_pdf") or not self.text_splitter:
            return {
                "status": "error",
                "message": f"Vector store unavailable: {self.initialization_error or 'initialization failed'}",
            }
        try:
            if not os.path.exists(pdf_path):
                logger.error(f"PDF file not found: {pdf_path}")
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")

            logger.info(f"Processing PDF: {pdf_path}")

            # Load PDF document
            loader = PyPDFLoader(pdf_path)
            documents = loader.load()
            logger.info(f"Loaded {len(documents)} pages from PDF")

            if not documents:
                logger.warning(f"No content found in PDF: {pdf_path}")
                return {"status": "warning", "message": "No content found in PDF"}

            # Split text into chunks
            texts = self.text_splitter.split_documents(documents)
            logger.info(f"Split into {len(texts)} chunks")

            # Get or create collection
            collection = self.create_collection("medical_documents")

            # Process in batches to avoid batch size limits
            batch_size = 100  # Process 100 chunks at a time
            total_added = 0

            for batch_start in range(0, len(texts), batch_size):
                batch_end = min(batch_start + batch_size, len(texts))
                batch_texts = texts[batch_start:batch_end]

                # Generate unique IDs for each chunk in this batch
                doc_ids = []
                documents_list = []
                metadatas_list = []

                for i, text in enumerate(batch_texts):
                    # Create unique ID based on content and filename
                    content_hash = hashlib.md5(text.page_content.encode()).hexdigest()
                    doc_id = f"{os.path.basename(pdf_path)}_{batch_start + i}_{content_hash[:8]}"

                    # Prepare metadata
                    doc_metadata = {
                        "source": pdf_path,
                        "page": text.metadata.get("page", batch_start + i),
                        "chunk": batch_start + i,
                        "total_chunks": len(texts),
                        "batch": batch_start // batch_size + 1,
                    }

                    if metadata:
                        doc_metadata.update(metadata)

                    doc_ids.append(doc_id)
                    documents_list.append(text.page_content)
                    metadatas_list.append(doc_metadata)

                # Add batch to collection
                collection.add(
                    documents=documents_list, metadatas=metadatas_list, ids=doc_ids
                )

                batch_added = len(batch_texts)
                total_added += batch_added
                logger.info(
                    f"Added batch {batch_start//batch_size + 1}: {batch_added} chunks (total: {total_added}/{len(texts)})"
                )

            logger.info(f"Successfully added {total_added} chunks to vector database")

            return {
                "status": "success",
                "message": "PDF converted to vectors successfully",
                "filename": os.path.basename(pdf_path),
                "pages": len(documents),
                "chunks": len(texts),
                "batches": (len(texts) + batch_size - 1) // batch_size,
                "collection": "medical_documents",
            }

        except Exception as e:
            logger.error(f"Error uploading PDF to vector DB: {str(e)}")
            raise

    def query(self, query_text: str, n_results: int = 5) -> Dict[str, Any]:
        """Query the vector database for similar documents"""
        if not self._is_available("query") or not self.client:
            return {
                "query": query_text,
                "results": [],
                "total_found": 0,
                "error": self.initialization_error or "vector store unavailable",
            }
        try:
            logger.info(f"Querying vector database: {query_text[:100]}...")

            collection = self.client.get_collection(DOC_COLLECTION_NAME)

            # Query the collection
            results = collection.query(
                query_texts=[query_text],
                n_results=n_results,
                include=["documents", "metadatas", "distances"],
            )

            logger.info(f"Found {len(results['documents'][0])} relevant chunks")

            # Process and format results
            formatted_results = []
            for i, (doc, metadata, distance) in enumerate(
                zip(
                    results["documents"][0],
                    results["metadatas"][0],
                    results["distances"][0],
                )
            ):
                formatted_results.append(
                    {
                        "content": doc,
                        "source": metadata.get("source", "Unknown"),
                        "page": metadata.get("page", 0),
                        "similarity_score": 1 - distance,
                        "chunk": metadata.get("chunk", i),
                        "generated": metadata.get("generated", False),
                        "generation_source": metadata.get("generation_source"),
                        "query_text": metadata.get("query_text", ""),
                        "response_text": metadata.get("response_text", ""),
                    }
                )

            return {
                "query": query_text,
                "results": formatted_results,
                "total_found": len(formatted_results),
            }

        except Exception as e:
            logger.error(f"Error querying vector database: {str(e)}")
            return {
                "query": query_text,
                "results": [],
                "total_found": 0,
                "error": str(e),
            }

    def store_generated_knowledge(
        self, query_text: str, response_text: str, source: str
    ) -> bool:
        """Store generated medical knowledge in the main document vector DB."""
        if not self._is_available("store_generated_knowledge"):
            return False
        try:
            if not query_text or not response_text:
                return False

            clean_response = self._strip_disclaimer(response_text)
            if len(clean_response.strip()) < 10:
                logger.info("Generated response too short to store in vector DB")
                return False

            collection = self.create_collection(DOC_COLLECTION_NAME)

            query_normalized = query_text.lower().strip()
            query_hash = hashlib.md5(query_normalized.encode()).hexdigest()
            doc_id = f"generated_{query_hash}"
            document_text = (
                f"Question: {query_text.strip()}\nAnswer: {clean_response.strip()}"
            )

            from datetime import datetime

            collection.upsert(
                ids=[doc_id],
                documents=[document_text],
                metadatas=[
                    {
                        "source": f"generated_{source}",
                        "page": 0,
                        "chunk": 0,
                        "generated": True,
                        "generation_source": source,
                        "query_text": query_text.strip()[:500],
                        "response_text": clean_response[:4000],
                        "query_hash": query_hash,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                ],
            )

            logger.info(
                f"Stored generated knowledge in {DOC_COLLECTION_NAME} (source={source}, id={doc_id})"
            )
            return True

        except Exception as e:
            logger.error(f"Error storing generated knowledge: {str(e)}")
            return False

    def get_collection_stats(
        self, collection_name: str = "medical_documents"
    ) -> Dict[str, Any]:
        """Get statistics about the collection"""
        if not self._is_available("get_collection_stats") or not self.client:
            return {
                "collection_name": collection_name,
                "error": self.initialization_error or "vector store unavailable",
            }
        try:
            collection = self.client.get_collection(collection_name)
            count = collection.count()

            # Get unique sources
            results = collection.get(include=["metadatas"])
            sources = set()
            for metadata in results["metadatas"]:
                sources.add(metadata.get("source", "Unknown"))

            logger.info(
                f"Collection stats: {count} documents from {len(sources)} sources"
            )

            return {
                "collection_name": collection_name,
                "total_documents": count,
                "sources": list(sources),
                "source_count": len(sources),
            }

        except Exception as e:
            logger.error(f"Error getting collection stats: {str(e)}")
            return {"collection_name": collection_name, "error": str(e)}

    def delete_document(self, source_path: str) -> Dict[str, Any]:
        """Delete all chunks from a specific source document"""
        if not self._is_available("delete_document") or not self.client:
            return {
                "status": "error",
                "message": self.initialization_error or "vector store unavailable",
            }
        try:
            collection = self.client.get_collection("medical_documents")

            # Get all documents from this source
            results = collection.get(where={"source": source_path})

            if results["ids"]:
                # Delete documents
                collection.delete(ids=results["ids"])
                logger.info(
                    f"Deleted {len(results['ids'])} documents from source: {source_path}"
                )

                return {
                    "status": "success",
                    "message": f"Deleted {len(results['ids'])} documents",
                    "deleted_count": len(results["ids"]),
                }
            else:
                logger.warning(f"No documents found for source: {source_path}")
                return {
                    "status": "warning",
                    "message": "No documents found for this source",
                }

        except Exception as e:
            logger.error(f"Error deleting documents: {str(e)}")
            raise

    def reset_collection(
        self, collection_name: str = "medical_documents"
    ) -> Dict[str, Any]:
        """Reset/clear the entire collection"""
        if not self._is_available("reset_collection") or not self.client:
            return {
                "status": "error",
                "message": self.initialization_error or "vector store unavailable",
            }
        try:
            self.client.delete_collection(collection_name)
            logger.info(f"Collection '{collection_name}' deleted")

            # Create fresh collection
            self.create_collection(collection_name)
            logger.info(f"Collection '{collection_name}' recreated")

            return {
                "status": "success",
                "message": f"Collection '{collection_name}' has been reset",
            }

        except Exception as e:
            logger.error(f"Error resetting collection: {str(e)}")
            raise

    def list_collections(self) -> List[str]:
        """List all available collections"""
        if not self._is_available("list_collections") or not self.client:
            return []
        try:
            collections = self.client.list_collections()
            collection_names = [col.name for col in collections]
            logger.info(f"Available collections: {collection_names}")
            return collection_names
        except Exception as e:
            logger.error(f"Error listing collections: {str(e)}")
            return []

    # ========== QUERY-RESPONSE PAIR CACHING ==========

    def find_cached_response(self, query_text: str) -> Optional[Dict[str, Any]]:
        """
        Search cached query-response pairs for a high-similarity match.
        Checks in-memory TTL cache first, then falls back to ChromaDB.
        Returns the stored response immediately if similarity >= SIMILARITY_THRESHOLD_DIRECT.
        """
        if not self._is_available("find_cached_response") or not self.client:
            return None
        # Check in-memory cache first
        cache_key = query_text.lower().strip()
        with self._cache_lock:
            if cache_key in self._response_cache:
                logger.info("In-memory cache HIT")
                return self._response_cache[cache_key]

        try:
            collection = self.client.get_collection(name=QR_COLLECTION_NAME)
            if collection.count() == 0:
                return None

            results = collection.query(
                query_texts=[query_text],
                n_results=1,
                include=["documents", "metadatas", "distances"],
            )

            if not results["documents"] or not results["documents"][0]:
                return None

            distance = results["distances"][0][0]
            similarity = 1 - distance

            logger.info(
                f"Cache lookup: best similarity={similarity:.4f} (threshold={SIMILARITY_THRESHOLD_DIRECT})"
            )

            if similarity >= SIMILARITY_THRESHOLD_DIRECT:
                metadata = results["metadatas"][0][0]
                cached_response = metadata.get("response_text", "")
                source = metadata.get("source", "vector_db")

                if cached_response and len(cached_response.strip()) > 10:
                    logger.info(
                        f"Cache HIT: returning stored response (similarity={similarity:.4f}, source={source})"
                    )
                    result = {
                        "response_text": cached_response,
                        "source": "vector_db",
                        "confidence": min(similarity, 0.98),
                        "original_source": source,
                        "cached": True,
                    }
                    # Populate in-memory cache
                    with self._cache_lock:
                        self._response_cache[cache_key] = result
                    return result

            logger.info(
                f"Cache MISS: similarity {similarity:.4f} < {SIMILARITY_THRESHOLD_DIRECT}"
            )
            return None

        except Exception as e:
            logger.error(f"Error in cached response lookup: {str(e)}")
            return None

    def store_query_response(
        self, query_text: str, response_text: str, source: str
    ) -> bool:
        """
        Store a query-response pair in the vector DB.
        Deduplicates: skips if an identical or near-identical query already exists.
        """
        if not self._is_available("store_query_response") or not self.client:
            return False
        try:
            if not query_text or not response_text:
                return False

            # Strip disclaimer from response before storing
            clean_response = self._strip_disclaimer(response_text)
            if len(clean_response.strip()) < 10:
                logger.info("Response too short to cache, skipping")
                return False

            collection = self.client.get_collection(name=QR_COLLECTION_NAME)

            # Deduplication: check if a very similar query already exists
            if collection.count() > 0:
                existing = collection.query(
                    query_texts=[query_text],
                    n_results=1,
                    include=["distances", "metadatas"],
                )
                if existing["distances"] and existing["distances"][0]:
                    best_similarity = 1 - existing["distances"][0][0]
                    if best_similarity >= 0.95:
                        logger.info(
                            f"Duplicate detected (similarity={best_similarity:.4f}), skipping store"
                        )
                        return False

            # Generate a unique ID from query content hash
            content_hash = hashlib.md5(query_text.lower().strip().encode()).hexdigest()
            doc_id = f"qr_{content_hash}"

            # Store with metadata
            from datetime import datetime

            collection.upsert(
                ids=[doc_id],
                documents=[query_text],
                metadatas=[
                    {
                        "response_text": clean_response[
                            :4000
                        ],  # ChromaDB metadata size limit
                        "source": source,
                        "timestamp": datetime.utcnow().isoformat(),
                        "query_hash": content_hash,
                    }
                ],
            )

            logger.info(f"Stored query-response pair (source={source}, id={doc_id})")
            return True

        except Exception as e:
            logger.error(f"Error storing query-response pair: {str(e)}")
            return False

    def update_cached_response(
        self, query_text: str, new_response: str, source: str
    ) -> bool:
        """Update an existing cached response for a query"""
        if not self._is_available("update_cached_response") or not self.client:
            return False
        try:
            collection = self.client.get_collection(name=QR_COLLECTION_NAME)
            content_hash = hashlib.md5(query_text.lower().strip().encode()).hexdigest()
            doc_id = f"qr_{content_hash}"

            clean_response = self._strip_disclaimer(new_response)

            from datetime import datetime

            collection.upsert(
                ids=[doc_id],
                documents=[query_text],
                metadatas=[
                    {
                        "response_text": clean_response[:4000],
                        "source": source,
                        "timestamp": datetime.utcnow().isoformat(),
                        "query_hash": content_hash,
                        "updated": "true",
                    }
                ],
            )

            logger.info(f"Updated cached response for query hash {content_hash}")
            return True

        except Exception as e:
            logger.error(f"Error updating cached response: {str(e)}")
            return False

    def delete_cached_response(self, query_text: str) -> bool:
        """Delete a cached response by query text"""
        if not self._is_available("delete_cached_response") or not self.client:
            return False
        try:
            collection = self.client.get_collection(name=QR_COLLECTION_NAME)
            content_hash = hashlib.md5(query_text.lower().strip().encode()).hexdigest()
            doc_id = f"qr_{content_hash}"

            collection.delete(ids=[doc_id])
            logger.info(f"Deleted cached response for query hash {content_hash}")
            return True

        except Exception as e:
            logger.error(f"Error deleting cached response: {str(e)}")
            return False

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the query-response cache"""
        if not self._is_available("get_cache_stats") or not self.client:
            return {"error": self.initialization_error or "vector store unavailable"}
        try:
            collection = self.client.get_collection(name=QR_COLLECTION_NAME)
            count = collection.count()

            stats = {"total_cached": count}

            if count > 0:
                results = collection.get(include=["metadatas"])
                sources = {}
                for meta in results["metadatas"]:
                    src = meta.get("source", "unknown")
                    sources[src] = sources.get(src, 0) + 1
                stats["by_source"] = sources

            return stats

        except Exception as e:
            logger.error(f"Error getting cache stats: {str(e)}")
            return {"error": str(e)}

    def _strip_disclaimer(self, text: str) -> str:
        """Remove the disclaimer suffix from a response before caching"""
        disclaimers = [
            "\n\nWichtiger Hinweis:",
            "\n\nImportant:",
            "\n\n(Low confidence)",
            "\n\n(Geringe Sicherheit)",
        ]
        for d in disclaimers:
            idx = text.find(d)
            if idx > 0:
                text = text[:idx]
        return text.strip()
