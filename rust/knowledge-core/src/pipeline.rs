use async_trait::async_trait;

use crate::{Chunker, Document, EmbeddedChunk, KnowledgeStore, Result, SearchHit};

#[async_trait]
pub trait DocumentExtractor: Send + Sync {
    async fn extract(&self, source_uri: &str, media_type: &str, bytes: &[u8]) -> Result<Document>;
}

#[async_trait]
pub trait Embedder: Send + Sync {
    async fn embed(&self, texts: &[String]) -> Result<Vec<Vec<f32>>>;
}

#[async_trait]
pub trait Reranker: Send + Sync {
    async fn rerank(&self, query: &str, hits: Vec<SearchHit>, limit: usize) -> Result<Vec<SearchHit>>;
}

pub struct KnowledgePipeline<E, C, M, S> {
    extractor: E,
    chunker: C,
    embedder: M,
    store: S,
}

impl<E, C, M, S> KnowledgePipeline<E, C, M, S>
where
    E: DocumentExtractor,
    C: Chunker,
    M: Embedder,
    S: KnowledgeStore,
{
    pub fn new(extractor: E, chunker: C, embedder: M, store: S) -> Self {
        Self { extractor, chunker, embedder, store }
    }

    pub async fn ingest(&self, source_uri: &str, media_type: &str, bytes: &[u8]) -> Result<usize> {
        let document = self.extractor.extract(source_uri, media_type, bytes).await?;
        let chunks = self.chunker.chunk(&document);
        let texts: Vec<String> = chunks.iter().map(|chunk| chunk.text.clone()).collect();
        let embeddings = self.embedder.embed(&texts).await?;
        if embeddings.len() != chunks.len() {
            return Err(crate::KnowledgeError::Embedding(format!(
                "embedder returned {} vectors for {} chunks",
                embeddings.len(), chunks.len()
            )));
        }
        let count = chunks.len();
        self.store.upsert(chunks.into_iter().zip(embeddings).map(|(chunk, embedding)| EmbeddedChunk { chunk, embedding }).collect())?;
        Ok(count)
    }

    pub async fn search(&self, query: &str, limit: usize) -> Result<Vec<SearchHit>> {
        let mut vectors = self.embedder.embed(&[query.to_owned()]).await?;
        let query_vector = vectors.pop().ok_or_else(|| crate::KnowledgeError::Embedding("embedder returned no query vector".into()))?;
        self.store.vector_search(&query_vector, limit)
    }
}
