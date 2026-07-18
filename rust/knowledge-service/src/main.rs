use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::net::SocketAddr;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use axum::extract::{Path as AxumPath, State};
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::routing::{delete, get, post};
use axum::{Json, Router};
use base64::engine::general_purpose::STANDARD as BASE64;
use base64::Engine;
use fastembed::{RerankInitOptions, TextInitOptions};
use rlm_knowledge_core::adapters::{FastEmbedEmbedder, FastEmbedReranker, XbergDocumentExtractor};
use rlm_knowledge_core::{
    Chunker, DocumentExtractor, EmbeddedChunk, Embedder, FixedWindowChunker,
    KnowledgeDocumentSummary, KnowledgeError, KnowledgeStats, KnowledgeStore, Reranker, SearchHit,
    SqliteKnowledgeStore,
};
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use tokio::sync::Mutex;
use tower_http::cors::CorsLayer;
use tower_http::trace::TraceLayer;

const DEFAULT_CANDIDATE_LIMIT: usize = 24;
const DEFAULT_RESULT_LIMIT: usize = 6;
const DEFAULT_CONTEXT_CHARS: usize = 24_000;

#[derive(Clone)]
struct AppState {
    inner: Arc<KnowledgeRuntime>,
}

struct KnowledgeRuntime {
    extractor: XbergDocumentExtractor,
    chunker: FixedWindowChunker,
    embedder: FastEmbedEmbedder,
    reranker: FastEmbedReranker,
    store: SqliteKnowledgeStore,
    database_path: PathBuf,
    mutation_gate: Mutex<()>,
}

#[derive(Debug, Deserialize)]
struct IngestRequest {
    source_uri: String,
    media_type: String,
    content_base64: String,
}

#[derive(Debug, Serialize)]
struct IngestResponse {
    document_id: String,
    source_uri: String,
    chunk_count: usize,
    replaced_document_ids: Vec<String>,
}

#[derive(Debug, Deserialize)]
struct SearchRequest {
    query: String,
    #[serde(default = "default_candidate_limit")]
    candidate_limit: usize,
    #[serde(default = "default_result_limit")]
    limit: usize,
    #[serde(default = "default_true")]
    rerank: bool,
    #[serde(default = "default_context_chars")]
    max_context_chars: usize,
}

#[derive(Debug, Serialize)]
struct Citation {
    index: usize,
    document_id: String,
    chunk_id: String,
    source_uri: Option<String>,
    media_type: Option<String>,
    title: Option<String>,
    score: f32,
}

#[derive(Debug, Serialize)]
struct SearchResponse {
    hits: Vec<SearchHit>,
    citations: Vec<Citation>,
    context: String,
}

#[derive(Debug, Serialize)]
struct DeleteResponse {
    document_id: String,
    deleted_chunks: usize,
}

#[derive(Debug, Serialize)]
struct HealthResponse {
    status: &'static str,
}

#[derive(Debug)]
struct ApiError {
    status: StatusCode,
    message: String,
}

impl ApiError {
    fn bad_request(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::BAD_REQUEST,
            message: message.into(),
        }
    }

    fn internal(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::INTERNAL_SERVER_ERROR,
            message: message.into(),
        }
    }
}

impl From<KnowledgeError> for ApiError {
    fn from(error: KnowledgeError) -> Self {
        Self::internal(error.to_string())
    }
}

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (
            self.status,
            Json(serde_json::json!({
                "error": {
                    "message": self.message,
                    "type": "knowledge_error"
                }
            })),
        )
            .into_response()
    }
}

fn default_candidate_limit() -> usize {
    DEFAULT_CANDIDATE_LIMIT
}

fn default_result_limit() -> usize {
    DEFAULT_RESULT_LIMIT
}

fn default_context_chars() -> usize {
    DEFAULT_CONTEXT_CHARS
}

fn default_true() -> bool {
    true
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "rlm_knowledge_service=info,tower_http=info".into()),
        )
        .init();

    let database_path = env::var_os("RLM_KNOWLEDGE_DB")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("rlm-knowledge.sqlite3"));
    ensure_parent(&database_path)?;

    let store = SqliteKnowledgeStore::open(&database_path)?;
    let runtime = KnowledgeRuntime {
        extractor: XbergDocumentExtractor::default(),
        chunker: FixedWindowChunker::default(),
        embedder: FastEmbedEmbedder::try_new(TextInitOptions::default(), Some(32))?,
        reranker: FastEmbedReranker::try_new(RerankInitOptions::default(), Some(32))?,
        store,
        database_path,
        mutation_gate: Mutex::new(()),
    };
    let state = AppState {
        inner: Arc::new(runtime),
    };

    let app = Router::new()
        .route("/healthz", get(healthz))
        .route("/v1/knowledge/ingest", post(ingest))
        .route("/v1/knowledge/search", post(search))
        .route("/v1/knowledge/documents", get(list_documents))
        .route(
            "/v1/knowledge/documents/{document_id}",
            delete(delete_document),
        )
        .route("/v1/knowledge/stats", get(stats))
        .layer(CorsLayer::permissive())
        .layer(TraceLayer::new_for_http())
        .with_state(state);

    let address: SocketAddr = env::var("RLM_KNOWLEDGE_BIND")
        .unwrap_or_else(|_| "127.0.0.1:8010".into())
        .parse()?;
    let listener = tokio::net::TcpListener::bind(address).await?;
    tracing::info!(%address, "knowledge service listening");
    axum::serve(listener, app)
        .with_graceful_shutdown(shutdown_signal())
        .await?;
    Ok(())
}

async fn healthz() -> Json<HealthResponse> {
    Json(HealthResponse { status: "ok" })
}

async fn ingest(
    State(state): State<AppState>,
    Json(request): Json<IngestRequest>,
) -> Result<Json<IngestResponse>, ApiError> {
    if request.source_uri.trim().is_empty() {
        return Err(ApiError::bad_request("source_uri must not be empty"));
    }
    let bytes = BASE64
        .decode(request.content_base64.as_bytes())
        .map_err(|error| ApiError::bad_request(format!("invalid content_base64: {error}")))?;

    let document = state
        .inner
        .extractor
        .extract(&request.source_uri, &request.media_type, &bytes)
        .await?;
    let chunks = state.inner.chunker.chunk(&document);
    if chunks.is_empty() {
        return Err(ApiError::bad_request("document produced no chunks"));
    }
    let texts: Vec<String> = chunks.iter().map(|chunk| chunk.text.clone()).collect();
    let embeddings = state.inner.embedder.embed(&texts).await?;
    if embeddings.len() != chunks.len() {
        return Err(ApiError::internal(format!(
            "embedder returned {} vectors for {} chunks",
            embeddings.len(),
            chunks.len()
        )));
    }
    let embedded: Vec<EmbeddedChunk> = chunks
        .into_iter()
        .zip(embeddings)
        .map(|(chunk, embedding)| EmbeddedChunk { chunk, embedding })
        .collect();

    let _guard = state.inner.mutation_gate.lock().await;
    let replaced_document_ids =
        document_ids_for_source(&state.inner.database_path, &request.source_uri)?;
    for document_id in &replaced_document_ids {
        delete_document_rows(&state.inner.database_path, document_id)?;
    }
    state.inner.store.upsert(embedded)?;

    Ok(Json(IngestResponse {
        document_id: document.id,
        source_uri: request.source_uri,
        chunk_count: texts.len(),
        replaced_document_ids,
    }))
}

async fn search(
    State(state): State<AppState>,
    Json(request): Json<SearchRequest>,
) -> Result<Json<SearchResponse>, ApiError> {
    if request.query.trim().is_empty() {
        return Err(ApiError::bad_request("query must not be empty"));
    }
    if request.limit == 0 {
        return Ok(Json(SearchResponse {
            hits: Vec::new(),
            citations: Vec::new(),
            context: String::new(),
        }));
    }

    let mut vectors = state.inner.embedder.embed(&[request.query.clone()]).await?;
    let query_vector = vectors
        .pop()
        .ok_or_else(|| ApiError::internal("embedder returned no query vector"))?;
    let candidate_limit = request.candidate_limit.max(request.limit);
    let candidates =
        state
            .inner
            .store
            .hybrid_search(&request.query, &query_vector, candidate_limit)?;
    let hits = if request.rerank {
        state
            .inner
            .reranker
            .rerank(&request.query, candidates, request.limit)
            .await?
    } else {
        candidates.into_iter().take(request.limit).collect()
    };
    let (context, citations) = build_context(&hits, request.max_context_chars);

    Ok(Json(SearchResponse {
        hits,
        citations,
        context,
    }))
}

async fn list_documents(
    State(state): State<AppState>,
) -> Result<Json<Vec<KnowledgeDocumentSummary>>, ApiError> {
    Ok(Json(read_documents(&state.inner.database_path)?))
}

async fn stats(State(state): State<AppState>) -> Result<Json<KnowledgeStats>, ApiError> {
    Ok(Json(read_stats(&state.inner.database_path)?))
}

async fn delete_document(
    State(state): State<AppState>,
    AxumPath(document_id): AxumPath<String>,
) -> Result<Json<DeleteResponse>, ApiError> {
    let _guard = state.inner.mutation_gate.lock().await;
    let deleted_chunks = delete_document_rows(&state.inner.database_path, &document_id)?;
    Ok(Json(DeleteResponse {
        document_id,
        deleted_chunks,
    }))
}

fn ensure_parent(path: &Path) -> std::io::Result<()> {
    if let Some(parent) = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
    {
        std::fs::create_dir_all(parent)?;
    }
    Ok(())
}

fn open_database(path: &Path) -> Result<Connection, ApiError> {
    Connection::open(path).map_err(|error| ApiError::internal(error.to_string()))
}

fn document_ids_for_source(path: &Path, source_uri: &str) -> Result<Vec<String>, ApiError> {
    let connection = open_database(path)?;
    let mut statement = connection
        .prepare("SELECT DISTINCT document_id, metadata_json FROM knowledge_chunks")
        .map_err(|error| ApiError::internal(error.to_string()))?;
    let rows = statement
        .query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })
        .map_err(|error| ApiError::internal(error.to_string()))?;
    let mut ids = BTreeSet::new();
    for row in rows {
        let (document_id, metadata_json) =
            row.map_err(|error| ApiError::internal(error.to_string()))?;
        let metadata: BTreeMap<String, String> = serde_json::from_str(&metadata_json)
            .map_err(|error| ApiError::internal(error.to_string()))?;
        if metadata.get("source_uri").map(String::as_str) == Some(source_uri) {
            ids.insert(document_id);
        }
    }
    Ok(ids.into_iter().collect())
}

fn delete_document_rows(path: &Path, document_id: &str) -> Result<usize, ApiError> {
    let mut connection = open_database(path)?;
    let transaction = connection
        .transaction()
        .map_err(|error| ApiError::internal(error.to_string()))?;
    transaction
        .execute(
            "DELETE FROM knowledge_chunks_fts
             WHERE id IN (SELECT id FROM knowledge_chunks WHERE document_id = ?1)",
            params![document_id],
        )
        .map_err(|error| ApiError::internal(error.to_string()))?;
    let deleted = transaction
        .execute(
            "DELETE FROM knowledge_chunks WHERE document_id = ?1",
            params![document_id],
        )
        .map_err(|error| ApiError::internal(error.to_string()))?;
    transaction
        .commit()
        .map_err(|error| ApiError::internal(error.to_string()))?;
    Ok(deleted)
}

fn read_documents(path: &Path) -> Result<Vec<KnowledgeDocumentSummary>, ApiError> {
    let connection = open_database(path)?;
    let mut statement = connection
        .prepare(
            "SELECT document_id, metadata_json, COUNT(*)
             FROM knowledge_chunks
             GROUP BY document_id
             ORDER BY document_id",
        )
        .map_err(|error| ApiError::internal(error.to_string()))?;
    let rows = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, i64>(2)?,
            ))
        })
        .map_err(|error| ApiError::internal(error.to_string()))?;
    let mut documents = Vec::new();
    for row in rows {
        let (document_id, metadata_json, chunk_count) =
            row.map_err(|error| ApiError::internal(error.to_string()))?;
        let metadata: BTreeMap<String, String> = serde_json::from_str(&metadata_json)
            .map_err(|error| ApiError::internal(error.to_string()))?;
        documents.push(KnowledgeDocumentSummary {
            document_id,
            source_uri: metadata.get("source_uri").cloned(),
            media_type: metadata.get("media_type").cloned(),
            title: metadata.get("title").cloned(),
            chunk_count: chunk_count as usize,
        });
    }
    Ok(documents)
}

fn read_stats(path: &Path) -> Result<KnowledgeStats, ApiError> {
    let connection = open_database(path)?;
    let document_count: i64 = connection
        .query_row(
            "SELECT COUNT(DISTINCT document_id) FROM knowledge_chunks",
            [],
            |row| row.get(0),
        )
        .map_err(|error| ApiError::internal(error.to_string()))?;
    let chunk_count: i64 = connection
        .query_row("SELECT COUNT(*) FROM knowledge_chunks", [], |row| {
            row.get(0)
        })
        .map_err(|error| ApiError::internal(error.to_string()))?;
    let mut statement = connection
        .prepare(
            "SELECT DISTINCT embedding_dimensions FROM knowledge_chunks ORDER BY embedding_dimensions",
        )
        .map_err(|error| ApiError::internal(error.to_string()))?;
    let dimensions = statement
        .query_map([], |row| row.get::<_, i64>(0))
        .map_err(|error| ApiError::internal(error.to_string()))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| ApiError::internal(error.to_string()))?;
    Ok(KnowledgeStats {
        document_count: document_count as usize,
        chunk_count: chunk_count as usize,
        embedding_dimensions: dimensions.into_iter().map(|value| value as usize).collect(),
    })
}

fn build_context(hits: &[SearchHit], max_chars: usize) -> (String, Vec<Citation>) {
    if max_chars == 0 {
        return (String::new(), Vec::new());
    }
    let mut context = String::new();
    let mut citations = Vec::new();
    for (position, hit) in hits.iter().enumerate() {
        let index = position + 1;
        let source_uri = hit.chunk.metadata.get("source_uri").cloned();
        let title = hit.chunk.metadata.get("title").cloned();
        let label = title
            .as_deref()
            .or(source_uri.as_deref())
            .unwrap_or(&hit.chunk.document_id);
        let section = format!("[Source {index}: {label}]\n{}\n", hit.chunk.text.trim());
        if context.len().saturating_add(section.len()) > max_chars {
            break;
        }
        context.push_str(&section);
        context.push('\n');
        citations.push(Citation {
            index,
            document_id: hit.chunk.document_id.clone(),
            chunk_id: hit.chunk.id.clone(),
            source_uri,
            media_type: hit.chunk.metadata.get("media_type").cloned(),
            title,
            score: hit.score,
        });
    }
    (context.trim_end().to_owned(), citations)
}

async fn shutdown_signal() {
    let ctrl_c = async {
        tokio::signal::ctrl_c()
            .await
            .expect("failed to install Ctrl+C handler");
    };

    #[cfg(unix)]
    let terminate = async {
        tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("failed to install signal handler")
            .recv()
            .await;
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        () = ctrl_c => {},
        () = terminate => {},
    }
}
