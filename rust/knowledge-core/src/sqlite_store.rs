use std::cmp::Ordering;
use std::collections::HashMap;
use std::path::Path;
use std::sync::Mutex;

use rusqlite::{params, Connection};

use crate::store::cosine_similarity;
use crate::{DocumentChunk, EmbeddedChunk, KnowledgeError, KnowledgeStore, Result, SearchHit};

const DEFAULT_RRF_K: usize = 60;
const DEFAULT_CANDIDATE_MULTIPLIER: usize = 4;

pub struct SqliteKnowledgeStore {
    connection: Mutex<Connection>,
}

impl SqliteKnowledgeStore {
    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        let connection = Connection::open(path).map_err(storage_error)?;
        Self::from_connection(connection)
    }

    pub fn in_memory() -> Result<Self> {
        let connection = Connection::open_in_memory().map_err(storage_error)?;
        Self::from_connection(connection)
    }

    fn from_connection(connection: Connection) -> Result<Self> {
        connection
            .execute_batch(
                "PRAGMA foreign_keys = ON;
                 CREATE TABLE IF NOT EXISTS knowledge_chunks (
                     id TEXT PRIMARY KEY,
                     document_id TEXT NOT NULL,
                     ordinal INTEGER NOT NULL,
                     text TEXT NOT NULL,
                     metadata_json TEXT NOT NULL,
                     embedding BLOB NOT NULL,
                     embedding_dimensions INTEGER NOT NULL
                 );
                 CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts USING fts5(
                     id UNINDEXED,
                     text,
                     tokenize = 'unicode61'
                 );",
            )
            .map_err(storage_error)?;
        Ok(Self {
            connection: Mutex::new(connection),
        })
    }

    pub fn lexical_search(&self, query: &str, limit: usize) -> Result<Vec<SearchHit>> {
        if query.trim().is_empty() || limit == 0 {
            return Ok(Vec::new());
        }

        let connection = self.connection.lock().map_err(storage_error)?;
        let mut statement = connection
            .prepare(
                "SELECT c.id, c.document_id, c.ordinal, c.text, c.metadata_json,
                        bm25(knowledge_chunks_fts) AS rank
                 FROM knowledge_chunks_fts
                 JOIN knowledge_chunks c ON c.id = knowledge_chunks_fts.id
                 WHERE knowledge_chunks_fts MATCH ?1
                 ORDER BY rank
                 LIMIT ?2",
            )
            .map_err(storage_error)?;
        let rows = statement
            .query_map(params![query, limit as i64], |row| {
                let metadata_json: String = row.get(4)?;
                let metadata = serde_json::from_str(&metadata_json).map_err(|error| {
                    rusqlite::Error::FromSqlConversionFailure(
                        4,
                        rusqlite::types::Type::Text,
                        Box::new(error),
                    )
                })?;
                let rank: f32 = row.get(5)?;
                Ok(SearchHit {
                    chunk: DocumentChunk {
                        id: row.get(0)?,
                        document_id: row.get(1)?,
                        ordinal: row.get::<_, i64>(2)? as usize,
                        text: row.get(3)?,
                        metadata,
                    },
                    score: -rank,
                })
            })
            .map_err(storage_error)?;

        rows.collect::<std::result::Result<Vec<_>, _>>()
            .map_err(storage_error)
    }

    pub fn hybrid_search(
        &self,
        text_query: &str,
        vector_query: &[f32],
        limit: usize,
    ) -> Result<Vec<SearchHit>> {
        if limit == 0 {
            return Ok(Vec::new());
        }

        let candidate_limit = limit.saturating_mul(DEFAULT_CANDIDATE_MULTIPLIER).max(limit);
        let lexical_hits = self.lexical_search(text_query, candidate_limit)?;
        let vector_hits = self.vector_search(vector_query, candidate_limit)?;
        Ok(fuse_ranked_lists(
            lexical_hits,
            vector_hits,
            limit,
            DEFAULT_RRF_K,
        ))
    }
}

impl KnowledgeStore for SqliteKnowledgeStore {
    fn upsert(&self, chunks: Vec<EmbeddedChunk>) -> Result<()> {
        if chunks.is_empty() {
            return Ok(());
        }

        let mut connection = self.connection.lock().map_err(storage_error)?;
        let transaction = connection.transaction().map_err(storage_error)?;
        for embedded in chunks {
            let metadata_json = serde_json::to_string(&embedded.chunk.metadata)
                .map_err(|error| KnowledgeError::Storage(error.to_string()))?;
            let embedding = encode_embedding(&embedded.embedding);
            transaction
                .execute(
                    "INSERT INTO knowledge_chunks
                        (id, document_id, ordinal, text, metadata_json, embedding, embedding_dimensions)
                     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)
                     ON CONFLICT(id) DO UPDATE SET
                        document_id = excluded.document_id,
                        ordinal = excluded.ordinal,
                        text = excluded.text,
                        metadata_json = excluded.metadata_json,
                        embedding = excluded.embedding,
                        embedding_dimensions = excluded.embedding_dimensions",
                    params![
                        &embedded.chunk.id,
                        &embedded.chunk.document_id,
                        embedded.chunk.ordinal as i64,
                        &embedded.chunk.text,
                        &metadata_json,
                        &embedding,
                        embedded.embedding.len() as i64,
                    ],
                )
                .map_err(storage_error)?;
            transaction
                .execute(
                    "DELETE FROM knowledge_chunks_fts WHERE id = ?1",
                    params![&embedded.chunk.id],
                )
                .map_err(storage_error)?;
            transaction
                .execute(
                    "INSERT INTO knowledge_chunks_fts (id, text) VALUES (?1, ?2)",
                    params![&embedded.chunk.id, &embedded.chunk.text],
                )
                .map_err(storage_error)?;
        }
        transaction.commit().map_err(storage_error)
    }

    fn vector_search(&self, query: &[f32], limit: usize) -> Result<Vec<SearchHit>> {
        if query.is_empty() || limit == 0 {
            return Ok(Vec::new());
        }

        let connection = self.connection.lock().map_err(storage_error)?;
        let mut statement = connection
            .prepare(
                "SELECT id, document_id, ordinal, text, metadata_json, embedding
                 FROM knowledge_chunks
                 WHERE embedding_dimensions = ?1",
            )
            .map_err(storage_error)?;
        let rows = statement
            .query_map(params![query.len() as i64], |row| {
                let metadata_json: String = row.get(4)?;
                let metadata = serde_json::from_str(&metadata_json).map_err(|error| {
                    rusqlite::Error::FromSqlConversionFailure(
                        4,
                        rusqlite::types::Type::Text,
                        Box::new(error),
                    )
                })?;
                let bytes: Vec<u8> = row.get(5)?;
                Ok((
                    DocumentChunk {
                        id: row.get(0)?,
                        document_id: row.get(1)?,
                        ordinal: row.get::<_, i64>(2)? as usize,
                        text: row.get(3)?,
                        metadata,
                    },
                    decode_embedding(&bytes),
                ))
            })
            .map_err(storage_error)?;

        let mut hits = Vec::new();
        for row in rows {
            let (chunk, embedding) = row.map_err(storage_error)?;
            if let Some(score) = cosine_similarity(query, &embedding) {
                hits.push(SearchHit { chunk, score });
            }
        }
        hits.sort_by(|left, right| {
            right
                .score
                .partial_cmp(&left.score)
                .unwrap_or(Ordering::Equal)
                .then_with(|| left.chunk.id.cmp(&right.chunk.id))
        });
        hits.truncate(limit);
        Ok(hits)
    }
}

fn fuse_ranked_lists(
    lexical_hits: Vec<SearchHit>,
    vector_hits: Vec<SearchHit>,
    limit: usize,
    rrf_k: usize,
) -> Vec<SearchHit> {
    let mut fused: HashMap<String, SearchHit> = HashMap::new();

    for (rank, hit) in lexical_hits.into_iter().enumerate() {
        add_rrf_score(&mut fused, hit, rank, rrf_k);
    }
    for (rank, hit) in vector_hits.into_iter().enumerate() {
        add_rrf_score(&mut fused, hit, rank, rrf_k);
    }

    let mut hits: Vec<SearchHit> = fused.into_values().collect();
    hits.sort_by(|left, right| {
        right
            .score
            .partial_cmp(&left.score)
            .unwrap_or(Ordering::Equal)
            .then_with(|| left.chunk.id.cmp(&right.chunk.id))
    });
    hits.truncate(limit);
    hits
}

fn add_rrf_score(
    fused: &mut HashMap<String, SearchHit>,
    mut hit: SearchHit,
    rank: usize,
    rrf_k: usize,
) {
    let contribution = 1.0 / (rrf_k + rank + 1) as f32;
    match fused.get_mut(&hit.chunk.id) {
        Some(existing) => existing.score += contribution,
        None => {
            hit.score = contribution;
            fused.insert(hit.chunk.id.clone(), hit);
        }
    }
}

fn encode_embedding(embedding: &[f32]) -> Vec<u8> {
    embedding
        .iter()
        .flat_map(|value| value.to_le_bytes())
        .collect()
}

fn decode_embedding(bytes: &[u8]) -> Vec<f32> {
    bytes
        .chunks_exact(4)
        .map(|chunk| f32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]))
        .collect()
}

fn storage_error(error: impl ToString) -> KnowledgeError {
    KnowledgeError::Storage(error.to_string())
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use super::*;

    fn embedded(id: &str, text: &str, embedding: Vec<f32>) -> EmbeddedChunk {
        EmbeddedChunk {
            chunk: DocumentChunk {
                id: id.into(),
                document_id: "doc".into(),
                ordinal: 0,
                text: text.into(),
                metadata: BTreeMap::from([("source_uri".into(), format!("memory://{id}"))]),
            },
            embedding,
        }
    }

    #[test]
    fn persists_and_ranks_vectors() {
        let store = SqliteKnowledgeStore::in_memory().unwrap();
        store
            .upsert(vec![
                embedded("rust", "Rust memory safety", vec![1.0, 0.0]),
                embedded("python", "Python runtime", vec![0.0, 1.0]),
            ])
            .unwrap();

        let hits = store.vector_search(&[1.0, 0.0], 1).unwrap();
        assert_eq!(hits[0].chunk.id, "rust");
        assert_eq!(
            hits[0].chunk.metadata.get("source_uri").map(String::as_str),
            Some("memory://rust")
        );
    }

    #[test]
    fn indexes_lexical_content_and_replaces_existing_chunks() {
        let store = SqliteKnowledgeStore::in_memory().unwrap();
        store
            .upsert(vec![embedded("chunk", "old python text", vec![0.0, 1.0])])
            .unwrap();
        store
            .upsert(vec![embedded("chunk", "new rust text", vec![1.0, 0.0])])
            .unwrap();

        assert!(store.lexical_search("python", 10).unwrap().is_empty());
        let hits = store.lexical_search("rust", 10).unwrap();
        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].chunk.text, "new rust text");
    }

    #[test]
    fn ignores_incompatible_vector_dimensions() {
        let store = SqliteKnowledgeStore::in_memory().unwrap();
        store
            .upsert(vec![embedded("chunk", "text", vec![1.0])])
            .unwrap();
        assert!(store.vector_search(&[1.0, 0.0], 10).unwrap().is_empty());
    }

    #[test]
    fn hybrid_search_rewards_candidates_present_in_both_rankings() {
        let store = SqliteKnowledgeStore::in_memory().unwrap();
        store
            .upsert(vec![
                embedded("both", "needle rust", vec![0.8, 0.2]),
                embedded("vector-only", "semantic candidate", vec![1.0, 0.0]),
                embedded("lexical-only", "needle exact", vec![0.0, 1.0]),
            ])
            .unwrap();

        let hits = store.hybrid_search("needle", &[1.0, 0.0], 3).unwrap();

        assert_eq!(hits[0].chunk.id, "both");
        assert_eq!(hits.len(), 3);
        assert!(hits[0].score > hits[1].score);
    }

    #[test]
    fn hybrid_search_handles_single_modality_and_zero_limit() {
        let store = SqliteKnowledgeStore::in_memory().unwrap();
        store
            .upsert(vec![embedded("rust", "rust exact", vec![1.0, 0.0])])
            .unwrap();

        assert_eq!(store.hybrid_search("", &[1.0, 0.0], 1).unwrap().len(), 1);
        assert_eq!(store.hybrid_search("rust", &[], 1).unwrap().len(), 1);
        assert!(store.hybrid_search("rust", &[1.0, 0.0], 0).unwrap().is_empty());
    }

    #[test]
    fn reciprocal_rank_fusion_deduplicates_and_applies_limit() {
        let chunk = embedded("same", "same", vec![1.0]).chunk;
        let lexical = vec![SearchHit {
            chunk: chunk.clone(),
            score: 10.0,
        }];
        let vector = vec![SearchHit { chunk, score: 1.0 }];

        let hits = fuse_ranked_lists(lexical, vector, 1, 60);

        assert_eq!(hits.len(), 1);
        assert_eq!(hits[0].chunk.id, "same");
        assert!(hits[0].score > 1.0 / 61.0);
    }
}
