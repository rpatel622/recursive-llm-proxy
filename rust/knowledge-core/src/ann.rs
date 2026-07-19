use crate::{EmbeddedChunk, KnowledgeStore, Result, SearchHit};

pub trait ApproximateKnowledgeStore: KnowledgeStore {
    fn approximate_search(
        &self,
        query: &[f32],
        candidate_limit: usize,
        limit: usize,
    ) -> Result<Vec<SearchHit>>;
}

pub struct ExactAnnAdapter<S> {
    inner: S,
}

impl<S> ExactAnnAdapter<S> {
    pub fn new(inner: S) -> Self {
        Self { inner }
    }

    pub fn inner(&self) -> &S {
        &self.inner
    }
}

impl<S> KnowledgeStore for ExactAnnAdapter<S>
where
    S: KnowledgeStore,
{
    fn upsert(&self, chunks: Vec<EmbeddedChunk>) -> Result<()> {
        self.inner.upsert(chunks)
    }

    fn vector_search(&self, query: &[f32], limit: usize) -> Result<Vec<SearchHit>> {
        self.inner.vector_search(query, limit)
    }
}

impl<S> ApproximateKnowledgeStore for ExactAnnAdapter<S>
where
    S: KnowledgeStore,
{
    fn approximate_search(
        &self,
        query: &[f32],
        candidate_limit: usize,
        limit: usize,
    ) -> Result<Vec<SearchHit>> {
        if limit == 0 {
            return Ok(Vec::new());
        }
        let mut hits = self.inner.vector_search(query, candidate_limit.max(limit))?;
        hits.truncate(limit);
        Ok(hits)
    }
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use crate::{DocumentChunk, EmbeddedChunk, InMemoryKnowledgeStore};

    use super::*;

    fn chunk(id: &str, vector: Vec<f32>) -> EmbeddedChunk {
        EmbeddedChunk {
            chunk: DocumentChunk {
                id: id.into(),
                document_id: "doc".into(),
                ordinal: 0,
                text: id.into(),
                metadata: BTreeMap::new(),
            },
            embedding: vector,
        }
    }

    #[test]
    fn exact_adapter_matches_vector_search_ordering() {
        let store = InMemoryKnowledgeStore::default();
        store
            .upsert(vec![
                chunk("best", vec![1.0, 0.0]),
                chunk("second", vec![0.8, 0.2]),
                chunk("far", vec![0.0, 1.0]),
            ])
            .unwrap();
        let adapter = ExactAnnAdapter::new(store);
        let exact = adapter.vector_search(&[1.0, 0.0], 2).unwrap();
        let approximate = adapter
            .approximate_search(&[1.0, 0.0], 3, 2)
            .unwrap();
        assert_eq!(
            exact.iter().map(|hit| &hit.chunk.id).collect::<Vec<_>>(),
            approximate
                .iter()
                .map(|hit| &hit.chunk.id)
                .collect::<Vec<_>>()
        );
    }

    #[test]
    fn candidate_limit_never_drops_below_result_limit() {
        let store = InMemoryKnowledgeStore::default();
        store
            .upsert(vec![
                chunk("one", vec![1.0, 0.0]),
                chunk("two", vec![0.9, 0.1]),
            ])
            .unwrap();
        let adapter = ExactAnnAdapter::new(store);
        assert_eq!(
            adapter
                .approximate_search(&[1.0, 0.0], 1, 2)
                .unwrap()
                .len(),
            2
        );
    }
}
