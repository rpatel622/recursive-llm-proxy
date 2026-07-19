//! Stable interfaces for the native Local RLM knowledge pipeline.

pub mod adapters;
mod cache;
mod chunking;
mod error;
mod model;
mod pipeline;
#[cfg(feature = "sqlite")]
mod sqlite_hybrid_store;
#[cfg(feature = "sqlite")]
mod sqlite_store;
mod store;

pub use cache::CachingEmbedder;
pub use chunking::{Chunker, FixedWindowChunker};
pub use error::{KnowledgeError, Result};
pub use model::{
    Document, DocumentChunk, EmbeddedChunk, KnowledgeDocumentSummary, KnowledgeStats, SearchHit,
};
pub use pipeline::{DocumentExtractor, Embedder, KnowledgePipeline, Reranker};
#[cfg(feature = "sqlite")]
pub use sqlite_store::SqliteKnowledgeStore;
pub use store::{HybridKnowledgeStore, InMemoryKnowledgeStore, KnowledgeStore};
