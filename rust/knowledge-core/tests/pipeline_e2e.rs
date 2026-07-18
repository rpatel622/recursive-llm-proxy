use std::collections::BTreeMap;

use async_trait::async_trait;
use rlm_knowledge_core::{
    Document, DocumentExtractor, Embedder, FixedWindowChunker, InMemoryKnowledgeStore,
    KnowledgePipeline, Result,
};

#[derive(Clone, Copy, Debug)]
struct PlainTextExtractor;

#[async_trait]
impl DocumentExtractor for PlainTextExtractor {
    async fn extract(&self, source_uri: &str, media_type: &str, bytes: &[u8]) -> Result<Document> {
        Ok(Document {
            id: source_uri.replace(['/', ':'], "-"),
            source_uri: source_uri.into(),
            media_type: media_type.into(),
            title: source_uri.rsplit('/').next().map(str::to_owned),
            text: String::from_utf8_lossy(bytes).into_owned(),
            metadata: BTreeMap::new(),
        })
    }
}

#[derive(Clone, Copy, Debug)]
struct KeywordEmbedder;

#[async_trait]
impl Embedder for KeywordEmbedder {
    async fn embed(&self, texts: &[String]) -> Result<Vec<Vec<f32>>> {
        Ok(texts.iter().map(|text| keyword_vector(text)).collect())
    }
}

fn keyword_vector(text: &str) -> Vec<f32> {
    let lowercase = text.to_lowercase();
    vec![
        lowercase.matches("rust").count() as f32,
        lowercase.matches("python").count() as f32,
        1.0,
    ]
}

#[tokio::test]
async fn ingests_and_retrieves_ranked_chunks_with_citations() {
    let pipeline = KnowledgePipeline::new(
        PlainTextExtractor,
        FixedWindowChunker::new(1_000, 0),
        KeywordEmbedder,
        InMemoryKnowledgeStore::default(),
    );

    pipeline
        .ingest(
            "memory://docs/rust.txt",
            "text/plain",
            b"Rust provides memory safety without a garbage collector.",
        )
        .await
        .unwrap();
    pipeline
        .ingest(
            "memory://docs/python.txt",
            "text/plain",
            b"Python emphasizes readability and a dynamic runtime.",
        )
        .await
        .unwrap();

    let hits = pipeline.search("Rust safety", 2).await.unwrap();

    assert_eq!(hits.len(), 2);
    assert!(hits[0].chunk.text.contains("Rust"));
    assert!(hits[0].score > hits[1].score);
    assert_eq!(
        hits[0].chunk.metadata.get("source_uri").map(String::as_str),
        Some("memory://docs/rust.txt")
    );
    assert_eq!(
        hits[0].chunk.metadata.get("media_type").map(String::as_str),
        Some("text/plain")
    );
    assert_eq!(
        hits[0].chunk.metadata.get("title").map(String::as_str),
        Some("rust.txt")
    );
}

#[tokio::test]
async fn zero_limit_search_skips_embedding_and_returns_no_hits() {
    let pipeline = KnowledgePipeline::new(
        PlainTextExtractor,
        FixedWindowChunker::default(),
        KeywordEmbedder,
        InMemoryKnowledgeStore::default(),
    );

    assert!(pipeline.search("anything", 0).await.unwrap().is_empty());
}

#[cfg(feature = "fastembed")]
#[tokio::test]
#[ignore = "downloads and initializes a real embedding model"]
async fn real_fastembed_smoke_test() {
    use fastembed::TextInitOptions;
    use rlm_knowledge_core::adapters::FastEmbedEmbedder;

    let options = TextInitOptions::default()
        .with_cache_dir(std::env::temp_dir().join("rlm-fastembed-smoke"))
        .with_show_download_progress(false)
        .with_intra_threads(1);
    let embedder = FastEmbedEmbedder::try_new(options, Some(1)).unwrap();
    let vectors = embedder.embed(&["local recursive language model".into()]).await.unwrap();

    assert_eq!(vectors.len(), 1);
    assert!(!vectors[0].is_empty());
}
