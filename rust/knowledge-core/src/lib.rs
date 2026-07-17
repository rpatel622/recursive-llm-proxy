//! Stable interfaces for the native Local RLM knowledge pipeline.

pub mod adapters;
mod chunking;
mod error;
mod model;
mod pipeline;
mod store;

pub use chunking::{Chunker, FixedWindowChunker};
pub use error::{KnowledgeError, Result};
pub use model::{Document, DocumentChunk, EmbeddedChunk, SearchHit};
pub use pipeline::{DocumentExtractor, Embedder, KnowledgePipeline, Reranker};
pub use store::{InMemoryKnowledgeStore, KnowledgeStore};
