use std::collections::BTreeMap;

use crate::{DocumentChunk, KnowledgeStore, Result, SearchHit};

pub const COLLECTION_METADATA_KEY: &str = "collection";
pub const NAMESPACE_METADATA_KEY: &str = "namespace";

#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct KnowledgeScope {
    pub collection: Option<String>,
    pub namespace: Option<String>,
    pub metadata: BTreeMap<String, String>,
}

impl KnowledgeScope {
    pub fn matches(&self, chunk: &DocumentChunk) -> bool {
        if let Some(collection) = &self.collection {
            if chunk.metadata.get(COLLECTION_METADATA_KEY) != Some(collection) {
                return false;
            }
        }
        if let Some(namespace) = &self.namespace {
            if chunk.metadata.get(NAMESPACE_METADATA_KEY) != Some(namespace) {
                return false;
            }
        }
        self.metadata
            .iter()
            .all(|(key, value)| chunk.metadata.get(key) == Some(value))
    }
}

pub trait ScopedKnowledgeStore: KnowledgeStore {
    fn vector_search_scoped(
        &self,
        query: &[f32],
        scope: &KnowledgeScope,
        candidate_limit: usize,
        limit: usize,
    ) -> Result<Vec<SearchHit>>;
}

pub struct ExactScopedAdapter<S> {
    inner: S,
}

impl<S> ExactScopedAdapter<S> {
    pub fn new(inner: S) -> Self {
        Self { inner }
    }

    pub fn inner(&self) -> &S {
        &self.inner
    }
}

impl<S> KnowledgeStore for ExactScopedAdapter<S>
where
    S: KnowledgeStore,
{
    fn upsert(&self, chunks: Vec<crate::EmbeddedChunk>) -> Result<()> {
        self.inner.upsert(chunks)
    }

    fn vector_search(&self, query: &[f32], limit: usize) -> Result<Vec<SearchHit>> {
        self.inner.vector_search(query, limit)
    }
}

impl<S> ScopedKnowledgeStore for ExactScopedAdapter<S>
where
    S: KnowledgeStore,
{
    fn vector_search_scoped(
        &self,
        query: &[f32],
        scope: &KnowledgeScope,
        candidate_limit: usize,
        limit: usize,
    ) -> Result<Vec<SearchHit>> {
        if limit == 0 {
            return Ok(Vec::new());
        }
        let mut hits = self.inner.vector_search(query, candidate_limit.max(limit))?;
        hits.retain(|hit| scope.matches(&hit.chunk));
        hits.truncate(limit);
        Ok(hits)
    }
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use crate::{DocumentChunk, EmbeddedChunk, InMemoryKnowledgeStore};

    use super::*;

    fn chunk(id: &str, collection: &str, namespace: &str, vector: Vec<f32>) -> EmbeddedChunk {
        let mut metadata = BTreeMap::new();
        metadata.insert(COLLECTION_METADATA_KEY.into(), collection.into());
        metadata.insert(NAMESPACE_METADATA_KEY.into(), namespace.into());
        EmbeddedChunk {
            chunk: DocumentChunk {
                id: id.into(),
                document_id: id.into(),
                ordinal: 0,
                text: id.into(),
                metadata,
            },
            embedding: vector,
        }
    }

    #[test]
    fn filters_collection_and_namespace() {
        let store = InMemoryKnowledgeStore::default();
        store
            .upsert(vec![
                chunk("one", "alpha", "prod", vec![1.0, 0.0]),
                chunk("two", "alpha", "dev", vec![0.9, 0.1]),
                chunk("three", "beta", "prod", vec![0.8, 0.2]),
            ])
            .unwrap();
        let adapter = ExactScopedAdapter::new(store);
        let scope = KnowledgeScope {
            collection: Some("alpha".into()),
            namespace: Some("prod".into()),
            metadata: BTreeMap::new(),
        };
        let hits = adapter
            .vector_search_scoped(&[1.0, 0.0], &scope, 10, 5)
            .unwrap();
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].chunk.id, "one");
    }

    #[test]
    fn applies_arbitrary_metadata_filters() {
        let mut metadata = BTreeMap::new();
        metadata.insert("owner".into(), "ops".into());
        let scope = KnowledgeScope {
            collection: None,
            namespace: None,
            metadata,
        };
        let mut chunk = chunk("one", "alpha", "prod", vec![1.0, 0.0]).chunk;
        chunk.metadata.insert("owner".into(), "ops".into());
        assert!(scope.matches(&chunk));
    }
}
