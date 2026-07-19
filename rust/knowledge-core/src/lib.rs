//! Stable interfaces for the native Local RLM knowledge pipeline.

pub mod adapters;
mod ann;
mod cache;
mod chunking;
mod error;
mod model;
mod pipeline;
mod scope;
#[cfg(feature = "sqlite")]
mod sqlite_hybrid_store;
#[cfg(feature = "sqlite")]
mod sqlite_store;
mod store;
mod sync;

pub use ann::{ApproximateKnowledgeStore, ExactAnnAdapter};
pub use cache::CachingEmbedder;
pub use chunking::{Chunker, FixedWindowChunker};
pub use error::{KnowledgeError, Result};
pub use model::{
    Document, DocumentChunk, EmbeddedChunk, KnowledgeDocumentSummary, KnowledgeStats, SearchHit,
};
pub use pipeline::{DocumentExtractor, Embedder, KnowledgePipeline, Reranker};
pub use scope::{
    ExactScopedAdapter, KnowledgeScope, ScopedKnowledgeStore, COLLECTION_METADATA_KEY,
    NAMESPACE_METADATA_KEY,
};
#[cfg(feature = "sqlite")]
pub use sqlite_store::SqliteKnowledgeStore;
pub use store::{HybridKnowledgeStore, InMemoryKnowledgeStore, KnowledgeStore};
pub use sync::{SourceFingerprint, SyncAction, SyncEntry, SyncManifest};
