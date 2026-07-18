use crate::{HybridKnowledgeStore, Result, SearchHit, SqliteKnowledgeStore};

impl HybridKnowledgeStore for SqliteKnowledgeStore {
    fn hybrid_search(
        &self,
        text_query: &str,
        vector_query: &[f32],
        limit: usize,
    ) -> Result<Vec<SearchHit>> {
        SqliteKnowledgeStore::hybrid_search(self, text_query, vector_query, limit)
    }
}
