use async_trait::async_trait;

use crate::{
    Chunker, Document, EmbeddedChunk, HybridKnowledgeStore, KnowledgeStore, Result, SearchHit,
};

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
    async fn rerank(
        &self,
        query: &str,
        hits: Vec<SearchHit>,
        limit: usize,
    ) -> Result<Vec<SearchHit>>;
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
        Self {
            extractor,
            chunker,
            embedder,
            store,
        }
    }

    pub async fn ingest(&self, source_uri: &str, media_type: &str, bytes: &[u8]) -> Result<usize> {
        let document = self
            .extractor
            .extract(source_uri, media_type, bytes)
            .await?;
        let chunks = self.chunker.chunk(&document);
        if chunks.is_empty() {
            return Ok(0);
        }

        let texts: Vec<String> = chunks.iter().map(|chunk| chunk.text.clone()).collect();
        let embeddings = self.embedder.embed(&texts).await?;
        if embeddings.len() != chunks.len() {
            return Err(crate::KnowledgeError::Embedding(format!(
                "embedder returned {} vectors for {} chunks",
                embeddings.len(),
                chunks.len()
            )));
        }

        let count = chunks.len();
        self.store.upsert(
            chunks
                .into_iter()
                .zip(embeddings)
                .map(|(chunk, embedding)| EmbeddedChunk { chunk, embedding })
                .collect(),
        )?;
        Ok(count)
    }

    pub async fn search(&self, query: &str, limit: usize) -> Result<Vec<SearchHit>> {
        if limit == 0 {
            return Ok(Vec::new());
        }

        let query_vector = self.embed_query(query).await?;
        self.store.vector_search(&query_vector, limit)
    }

    async fn embed_query(&self, query: &str) -> Result<Vec<f32>> {
        let mut vectors = self.embedder.embed(&[query.to_owned()]).await?;
        vectors.pop().ok_or_else(|| {
            crate::KnowledgeError::Embedding("embedder returned no query vector".into())
        })
    }
}

impl<E, C, M, S> KnowledgePipeline<E, C, M, S>
where
    E: DocumentExtractor,
    C: Chunker,
    M: Embedder,
    S: HybridKnowledgeStore,
{
    pub async fn search_hybrid(&self, query: &str, limit: usize) -> Result<Vec<SearchHit>> {
        if limit == 0 {
            return Ok(Vec::new());
        }

        let query_vector = self.embed_query(query).await?;
        self.store.hybrid_search(query, &query_vector, limit)
    }

    pub async fn search_hybrid_reranked<R>(
        &self,
        query: &str,
        candidate_limit: usize,
        limit: usize,
        reranker: &R,
    ) -> Result<Vec<SearchHit>>
    where
        R: Reranker,
    {
        if limit == 0 {
            return Ok(Vec::new());
        }

        let candidate_limit = candidate_limit.max(limit);
        let hits = self.search_hybrid(query, candidate_limit).await?;
        reranker.rerank(query, hits, limit).await
    }
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;
    use std::sync::atomic::{AtomicUsize, Ordering};

    use crate::{DocumentChunk, KnowledgeError};

    use super::*;

    struct NoopExtractor;

    #[async_trait]
    impl DocumentExtractor for NoopExtractor {
        async fn extract(
            &self,
            _source_uri: &str,
            _media_type: &str,
            _bytes: &[u8],
        ) -> Result<Document> {
            Err(KnowledgeError::Extraction("unused".into()))
        }
    }

    struct NoopChunker;

    impl Chunker for NoopChunker {
        fn chunk(&self, _document: &Document) -> Vec<DocumentChunk> {
            Vec::new()
        }
    }

    struct FixedEmbedder;

    #[async_trait]
    impl Embedder for FixedEmbedder {
        async fn embed(&self, texts: &[String]) -> Result<Vec<Vec<f32>>> {
            Ok(texts.iter().map(|_| vec![1.0, 0.0]).collect())
        }
    }

    #[derive(Default)]
    struct RecordingHybridStore {
        requested_limit: AtomicUsize,
    }

    impl KnowledgeStore for RecordingHybridStore {
        fn upsert(&self, _chunks: Vec<EmbeddedChunk>) -> Result<()> {
            Ok(())
        }

        fn vector_search(&self, _query: &[f32], _limit: usize) -> Result<Vec<SearchHit>> {
            Ok(Vec::new())
        }
    }

    impl HybridKnowledgeStore for RecordingHybridStore {
        fn hybrid_search(
            &self,
            _text_query: &str,
            _vector_query: &[f32],
            limit: usize,
        ) -> Result<Vec<SearchHit>> {
            self.requested_limit.store(limit, Ordering::SeqCst);
            Ok((0..limit).map(hit).collect())
        }
    }

    struct ReverseReranker;

    #[async_trait]
    impl Reranker for ReverseReranker {
        async fn rerank(
            &self,
            _query: &str,
            mut hits: Vec<SearchHit>,
            limit: usize,
        ) -> Result<Vec<SearchHit>> {
            hits.reverse();
            hits.truncate(limit);
            Ok(hits)
        }
    }

    fn hit(index: usize) -> SearchHit {
        SearchHit {
            chunk: DocumentChunk {
                id: format!("chunk-{index}"),
                document_id: "doc".into(),
                ordinal: index,
                text: format!("text {index}"),
                metadata: BTreeMap::new(),
            },
            score: index as f32,
        }
    }

    #[tokio::test]
    async fn hybrid_search_embeds_query_and_uses_requested_limit() {
        let pipeline = KnowledgePipeline::new(
            NoopExtractor,
            NoopChunker,
            FixedEmbedder,
            RecordingHybridStore::default(),
        );

        let hits = pipeline.search_hybrid("rust", 2).await.unwrap();

        assert_eq!(hits.len(), 2);
        assert_eq!(pipeline.store.requested_limit.load(Ordering::SeqCst), 2);
    }

    #[tokio::test]
    async fn reranked_search_widens_candidates_to_final_limit() {
        let pipeline = KnowledgePipeline::new(
            NoopExtractor,
            NoopChunker,
            FixedEmbedder,
            RecordingHybridStore::default(),
        );

        let hits = pipeline
            .search_hybrid_reranked("rust", 1, 2, &ReverseReranker)
            .await
            .unwrap();

        assert_eq!(pipeline.store.requested_limit.load(Ordering::SeqCst), 2);
        assert_eq!(hits.len(), 2);
        assert_eq!(hits[0].chunk.id, "chunk-1");
    }

    #[tokio::test]
    async fn zero_limit_hybrid_search_skips_store() {
        let pipeline = KnowledgePipeline::new(
            NoopExtractor,
            NoopChunker,
            FixedEmbedder,
            RecordingHybridStore::default(),
        );

        assert!(pipeline.search_hybrid("rust", 0).await.unwrap().is_empty());
        assert_eq!(pipeline.store.requested_limit.load(Ordering::SeqCst), 0);
    }
}
