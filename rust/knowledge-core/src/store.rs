use std::cmp::Ordering;
use std::sync::RwLock;

use crate::{EmbeddedChunk, Result, SearchHit};

pub trait KnowledgeStore: Send + Sync {
    fn upsert(&self, chunks: Vec<EmbeddedChunk>) -> Result<()>;
    fn vector_search(&self, query: &[f32], limit: usize) -> Result<Vec<SearchHit>>;
}

pub trait HybridKnowledgeStore: KnowledgeStore {
    fn hybrid_search(
        &self,
        text_query: &str,
        vector_query: &[f32],
        limit: usize,
    ) -> Result<Vec<SearchHit>>;
}

#[derive(Default)]
pub struct InMemoryKnowledgeStore {
    chunks: RwLock<Vec<EmbeddedChunk>>,
}

impl KnowledgeStore for InMemoryKnowledgeStore {
    fn upsert(&self, chunks: Vec<EmbeddedChunk>) -> Result<()> {
        let mut stored = self
            .chunks
            .write()
            .map_err(|error| crate::KnowledgeError::Storage(error.to_string()))?;
        for incoming in chunks {
            stored.retain(|existing| existing.chunk.id != incoming.chunk.id);
            stored.push(incoming);
        }
        Ok(())
    }

    fn vector_search(&self, query: &[f32], limit: usize) -> Result<Vec<SearchHit>> {
        if limit == 0 {
            return Ok(Vec::new());
        }

        let stored = self
            .chunks
            .read()
            .map_err(|error| crate::KnowledgeError::Storage(error.to_string()))?;
        let mut hits: Vec<SearchHit> = stored
            .iter()
            .filter_map(|item| {
                cosine_similarity(query, &item.embedding).map(|score| SearchHit {
                    chunk: item.chunk.clone(),
                    score,
                })
            })
            .collect();
        hits.sort_by(|left, right| {
            right
                .score
                .partial_cmp(&left.score)
                .unwrap_or(Ordering::Equal)
        });
        hits.truncate(limit);
        Ok(hits)
    }
}

pub(crate) fn cosine_similarity(left: &[f32], right: &[f32]) -> Option<f32> {
    if left.len() != right.len() || left.is_empty() {
        return None;
    }
    let dot: f32 = left.iter().zip(right).map(|(a, b)| a * b).sum();
    let left_norm: f32 = left.iter().map(|value| value * value).sum::<f32>().sqrt();
    let right_norm: f32 = right.iter().map(|value| value * value).sum::<f32>().sqrt();
    (left_norm > 0.0 && right_norm > 0.0).then_some(dot / (left_norm * right_norm))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::DocumentChunk;
    use std::collections::BTreeMap;

    #[test]
    fn ranks_cosine_similarity() {
        let store = InMemoryKnowledgeStore::default();
        let chunk = |id: &str, embedding| EmbeddedChunk {
            chunk: DocumentChunk {
                id: id.into(),
                document_id: "d".into(),
                ordinal: 0,
                text: id.into(),
                metadata: BTreeMap::new(),
            },
            embedding,
        };
        store
            .upsert(vec![
                chunk("near", vec![1.0, 0.0]),
                chunk("far", vec![0.0, 1.0]),
            ])
            .unwrap();
        assert_eq!(
            store.vector_search(&[1.0, 0.0], 1).unwrap()[0].chunk.id,
            "near"
        );
    }

    #[test]
    fn ignores_incompatible_and_zero_vectors() {
        let store = InMemoryKnowledgeStore::default();
        let make_chunk = |id: &str, embedding| EmbeddedChunk {
            chunk: DocumentChunk {
                id: id.into(),
                document_id: "d".into(),
                ordinal: 0,
                text: id.into(),
                metadata: BTreeMap::new(),
            },
            embedding,
        };
        store
            .upsert(vec![
                make_chunk("wrong-size", vec![1.0]),
                make_chunk("zero", vec![0.0, 0.0]),
            ])
            .unwrap();
        assert!(store.vector_search(&[1.0, 0.0], 10).unwrap().is_empty());
    }
}
