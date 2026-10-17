"""
System Role: Singleton connection manager providing authenticated AsyncQdrantClient instances.
Inputs: Centralized host, REST/gRPC ports, transport preference, timeout and credential settings from config.
Note: gRPC is preferred — measured 2.4 ms vs 48 ms per search over REST (TCP delayed-ACK on large JSON bodies),
      while Qdrant itself spends ~0.8 ms.
Outputs: Active, managed AsyncQdrantClient connection session.
Ref: ARCHITECTURE.md §3 & §5 Centralized Config Principle
"""

import logging
from typing import Optional
from qdrant_client import AsyncQdrantClient

from config import settings

logger = logging.getLogger("rag_engine.vectordb.client")

_CLIENT_INSTANCE: Optional[AsyncQdrantClient] = None


def get_qdrant_client() -> AsyncQdrantClient:
    """
    Returns the singleton AsyncQdrantClient instance.
    Initializes connection on first invocation using centralized settings.
    """
    global _CLIENT_INSTANCE
    if _CLIENT_INSTANCE is None:
        transport = f"gRPC :{settings.qdrant_grpc_port}" if settings.qdrant_prefer_grpc else f"REST :{settings.qdrant_port}"
        logger.info(f"Connecting to Qdrant at {settings.qdrant_host} ({transport})...")
        _CLIENT_INSTANCE = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            grpc_port=settings.qdrant_grpc_port,
            prefer_grpc=settings.qdrant_prefer_grpc,
            api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
            timeout=settings.qdrant_timeout_seconds,
        )

    return _CLIENT_INSTANCE


def set_qdrant_client(client: AsyncQdrantClient) -> None:
    """Sets or overrides the active AsyncQdrantClient instance (useful for testing)."""
    global _CLIENT_INSTANCE
    _CLIENT_INSTANCE = client


async def close_qdrant_client() -> None:
    """Closes and releases the active Qdrant client connection pool."""
    global _CLIENT_INSTANCE
    if _CLIENT_INSTANCE is not None:
        logger.info("Closing Qdrant client connection...")
        await _CLIENT_INSTANCE.close()
        _CLIENT_INSTANCE = None

