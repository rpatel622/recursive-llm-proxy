use std::sync::Mutex;

use async_trait::async_trait;
use fastembed::{RerankInitOptions, TextEmbedding, TextInitOptions, TextRerank};

use crate::{Embedder, KnowledgeError, Reranker, Result, SearchHit};

pub struct FastEmbedEmbedder {
    model: Mutex<TextEmbedding>,
    batch_size: Option<usize>,
}

impl FastEmbedEmbedder {
    pub fn try_new(options: TextInitOptions, batch_size: Option<usize>) -> Result<Self> {
        validate_batch_size(batch_size)?;
        let model = TextEmbedding::try_new(options)
            .map_err(|error| KnowledgeError::Embedding(error.to_string()))?;
        Ok(Self {
            model: Mutex::new(model),
            batch_size,
        })
    }
}

#[async_trait]
impl Embedder for FastEmbedEmbedder {
    async fn embed(&self, texts: &[String]) -> Result<Vec<Vec<f32>>> {
        if texts.is_empty() {
            return Ok(Vec::new());
        }

        let mut model = self
            .model
            .lock()
            .map_err(|error| KnowledgeError::Embedding(error.to_string()))?;
        model
            .embed(texts, self.batch_size)
            .map_err(|error| KnowledgeError::Embedding(error.to_string()))
    }
}

pub struct FastEmbedReranker {
    model: Mutex<TextRerank>,
    batch_size: Option<usize>,
}

impl FastEmbedReranker {
    pub fn try_new(options: RerankInitOptions, batch_size: Option<usize>) -> Result<Self> {
        validate_batch_size(batch_size)?;
        let model = TextRerank::try_new(options)
            .map_err(|error| KnowledgeError::Embedding(error.to_string()))?;
        Ok(Self {
            model: Mutex::new(model),
            batch_size,
        })
    }
}

#[async_trait]
impl Reranker for FastEmbedReranker {
    async fn rerank(
        &self,
        query: &str,
        hits: Vec<SearchHit>,
        limit: usize,
    ) -> Result<Vec<SearchHit>> {
        if hits.is_empty() || limit == 0 {
            return Ok(Vec::new());
        }

        let documents: Vec<&str> = hits.iter().map(|hit| hit.chunk.text.as_str()).collect();
        let mut model = self
            .model
            .lock()
            .map_err(|error| KnowledgeError::Embedding(error.to_string()))?;
        let ranked = model
            .rerank(query, &documents, false, self.batch_size)
            .map_err(|error| KnowledgeError::Embedding(error.to_string()))?;
        let scores = ranked.into_iter().map(|item| (item.index, item.score));
        apply_rerank_scores(hits, scores, limit)
    }
}

fn validate_batch_size(batch_size: Option<usize>) -> Result<()> {
    if batch_size == Some(0) {
        return Err(KnowledgeError::Configuration(
            "batch_size must be greater than zero".into(),
        ));
    }
    Ok(())
}

fn apply_rerank_scores(
    hits: Vec<SearchHit>,
    scores: impl IntoIterator<Item = (usize, f32)>,
    limit: usize,
) -> Result<Vec<SearchHit>> {
    let mut slots: Vec<Option<SearchHit>> = hits.into_iter().map(Some).collect();
    let mut reranked = Vec::new();

    for (index, score) in scores {
        let hit = slots
            .get_mut(index)
            .and_then(Option::take)
            .ok_or_else(|| {
                KnowledgeError::Embedding(format!(
                    "reranker returned invalid or duplicate document index {index}"
                ))
            })?;
        reranked.push(SearchHit { score, ..hit });
        if reranked.len() == limit {
            break;
        }
    }

    Ok(reranked)
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use crate::DocumentChunk;

    use super::*;

    fn hit(id: &str, score: f32) -> SearchHit {
        SearchHit {
            chunk: DocumentChunk {
                id: id.into(),
                document_id: "doc".into(),
                ordinal: 0,
                text: id.into(),
                metadata: BTreeMap::new(),
            },
            score,
        }
    }

    #[test]
    fn rejects_zero_batch_size() {
        assert!(validate_batch_size(Some(0)).is_err());
        assert!(validate_batch_size(Some(1)).is_ok());
        assert!(validate_batch_size(None).is_ok());
    }

    #[test]
    fn applies_scores_in_reranker_order_and_limit() {
        let reranked = apply_rerank_scores(
            vec![hit("first", 0.1), hit("second", 0.2), hit("third", 0.3)],
            [(2, 9.0), (0, 8.0), (1, 7.0)],
            2,
        )
        .unwrap();

        assert_eq!(reranked.len(), 2);
        assert_eq!(reranked[0].chunk.id, "third");
        assert_eq!(reranked[0].score, 9.0);
        assert_eq!(reranked[1].chunk.id, "first");
    }

    #[test]
    fn rejects_invalid_or_duplicate_indexes() {
        assert!(apply_rerank_scores(vec![hit("only", 0.0)], [(1, 1.0)], 1).is_err());
        assert!(apply_rerank_scores(vec![hit("only", 0.0)], [(0, 1.0), (0, 0.5)], 2).is_err());
    }
}
