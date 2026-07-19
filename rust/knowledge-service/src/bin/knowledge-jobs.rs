use std::env;
use std::net::SocketAddr;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use axum::extract::{Path as AxumPath, State};
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::routing::{delete, get, post};
use axum::{Json, Router};
use reqwest::Client;
use rusqlite::{params, Connection, OptionalExtension};
use serde::{Deserialize, Serialize};
use tokio::sync::Semaphore;
use tower_http::cors::CorsLayer;
use tower_http::trace::TraceLayer;

static JOB_SEQUENCE: AtomicU64 = AtomicU64::new(0);

#[derive(Clone)]
struct AppState {
    inner: Arc<JobRuntime>,
}

struct JobRuntime {
    database_path: PathBuf,
    knowledge_api_base: String,
    client: Client,
    permits: Arc<Semaphore>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct IngestPayload {
    source_uri: String,
    media_type: String,
    content_base64: String,
}

#[derive(Debug, Deserialize)]
struct EnqueueRequest {
    #[serde(flatten)]
    payload: IngestPayload,
}

#[derive(Clone, Debug, Serialize)]
struct JobRecord {
    id: String,
    status: String,
    source_uri: String,
    media_type: String,
    created_at_ms: i64,
    updated_at_ms: i64,
    error: Option<String>,
    result: Option<serde_json::Value>,
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

    fn not_found(message: impl Into<String>) -> Self {
        Self {
            status: StatusCode::NOT_FOUND,
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

impl IntoResponse for ApiError {
    fn into_response(self) -> Response {
        (
            self.status,
            Json(serde_json::json!({
                "error": {"message": self.message, "type": "knowledge_job_error"}
            })),
        )
            .into_response()
    }
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "knowledge_jobs=info,tower_http=info".into()),
        )
        .init();

    let database_path = env::var_os("RLM_KNOWLEDGE_JOBS_DB")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("rlm-knowledge-jobs.sqlite3"));
    ensure_parent(&database_path)?;
    migrate(&database_path)?;
    recover_interrupted_jobs(&database_path)?;

    let concurrency = env::var("RLM_KNOWLEDGE_JOB_CONCURRENCY")
        .ok()
        .and_then(|value| value.parse::<usize>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(2);
    let runtime = Arc::new(JobRuntime {
        database_path,
        knowledge_api_base: env::var("RLM_KNOWLEDGE_API_BASE")
            .unwrap_or_else(|_| "http://127.0.0.1:8010".into())
            .trim_end_matches('/')
            .to_owned(),
        client: Client::new(),
        permits: Arc::new(Semaphore::new(concurrency)),
    });

    for job_id in queued_job_ids(&runtime.database_path)? {
        spawn_job(runtime.clone(), job_id);
    }

    let state = AppState { inner: runtime };
    let app = Router::new()
        .route("/healthz", get(healthz))
        .route("/v1/knowledge/jobs", post(enqueue).get(list_jobs))
        .route(
            "/v1/knowledge/jobs/{job_id}",
            get(get_job).delete(cancel_job),
        )
        .layer(CorsLayer::permissive())
        .layer(TraceLayer::new_for_http())
        .with_state(state);

    let address: SocketAddr = env::var("RLM_KNOWLEDGE_JOBS_BIND")
        .unwrap_or_else(|_| "127.0.0.1:8011".into())
        .parse()?;
    let listener = tokio::net::TcpListener::bind(address).await?;
    tracing::info!(%address, "knowledge job service listening");
    axum::serve(listener, app).await?;
    Ok(())
}

async fn healthz() -> Json<HealthResponse> {
    Json(HealthResponse { status: "ok" })
}

async fn enqueue(
    State(state): State<AppState>,
    Json(request): Json<EnqueueRequest>,
) -> Result<(StatusCode, Json<JobRecord>), ApiError> {
    if request.payload.source_uri.trim().is_empty() {
        return Err(ApiError::bad_request("source_uri must not be empty"));
    }
    if request.payload.media_type.trim().is_empty() {
        return Err(ApiError::bad_request("media_type must not be empty"));
    }
    if request.payload.content_base64.is_empty() {
        return Err(ApiError::bad_request("content_base64 must not be empty"));
    }

    let job_id = next_job_id();
    insert_job(&state.inner.database_path, &job_id, &request.payload)?;
    let record = read_job(&state.inner.database_path, &job_id)?
        .ok_or_else(|| ApiError::internal("created job could not be read"))?;
    spawn_job(state.inner.clone(), job_id);
    Ok((StatusCode::ACCEPTED, Json(record)))
}

async fn list_jobs(State(state): State<AppState>) -> Result<Json<Vec<JobRecord>>, ApiError> {
    Ok(Json(read_jobs(&state.inner.database_path)?))
}

async fn get_job(
    State(state): State<AppState>,
    AxumPath(job_id): AxumPath<String>,
) -> Result<Json<JobRecord>, ApiError> {
    read_job(&state.inner.database_path, &job_id)?
        .map(Json)
        .ok_or_else(|| ApiError::not_found(format!("unknown job: {job_id}")))
}

async fn cancel_job(
    State(state): State<AppState>,
    AxumPath(job_id): AxumPath<String>,
) -> Result<Json<JobRecord>, ApiError> {
    let connection = open_database(&state.inner.database_path)?;
    let changed = connection
        .execute(
            "UPDATE knowledge_jobs
             SET status = 'cancelled', updated_at_ms = ?2
             WHERE id = ?1 AND status IN ('queued', 'running')",
            params![job_id, now_ms()],
        )
        .map_err(|error| ApiError::internal(error.to_string()))?;
    if changed == 0 && read_job(&state.inner.database_path, &job_id)?.is_none() {
        return Err(ApiError::not_found(format!("unknown job: {job_id}")));
    }
    read_job(&state.inner.database_path, &job_id)?
        .map(Json)
        .ok_or_else(|| ApiError::internal("cancelled job could not be read"))
}

fn spawn_job(runtime: Arc<JobRuntime>, job_id: String) {
    tokio::spawn(async move {
        if let Err(error) = process_job(runtime.clone(), &job_id).await {
            tracing::error!(%job_id, %error, "knowledge ingestion job failed");
            let _ = finish_job(
                &runtime.database_path,
                &job_id,
                "failed",
                Some(error.to_string()),
                None,
            );
        }
    });
}

async fn process_job(runtime: Arc<JobRuntime>, job_id: &str) -> Result<(), ApiError> {
    let _permit = runtime
        .permits
        .acquire()
        .await
        .map_err(|error| ApiError::internal(error.to_string()))?;
    if job_status(&runtime.database_path, job_id)?.as_deref() == Some("cancelled") {
        return Ok(());
    }
    mark_running(&runtime.database_path, job_id)?;
    let payload = read_payload(&runtime.database_path, job_id)?
        .ok_or_else(|| ApiError::not_found(format!("unknown job: {job_id}")))?;
    let response = runtime
        .client
        .post(format!("{}/v1/knowledge/ingest", runtime.knowledge_api_base))
        .json(&payload)
        .send()
        .await
        .map_err(|error| ApiError::internal(error.to_string()))?;
    let status = response.status();
    let value: serde_json::Value = response
        .json()
        .await
        .map_err(|error| ApiError::internal(error.to_string()))?;
    if job_status(&runtime.database_path, job_id)?.as_deref() == Some("cancelled") {
        return Ok(());
    }
    if !status.is_success() {
        return Err(ApiError::internal(format!(
            "knowledge service returned {status}: {value}"
        )));
    }
    finish_job(
        &runtime.database_path,
        job_id,
        "succeeded",
        None,
        Some(value),
    )?;
    Ok(())
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

fn migrate(path: &Path) -> Result<(), ApiError> {
    let connection = open_database(path)?;
    connection
        .execute_batch(
            "CREATE TABLE IF NOT EXISTS knowledge_jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                source_uri TEXT NOT NULL,
                media_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at_ms INTEGER NOT NULL,
                updated_at_ms INTEGER NOT NULL,
                error TEXT,
                result_json TEXT
            );
            CREATE INDEX IF NOT EXISTS knowledge_jobs_status_created
            ON knowledge_jobs(status, created_at_ms);",
        )
        .map_err(|error| ApiError::internal(error.to_string()))
}

fn recover_interrupted_jobs(path: &Path) -> Result<(), ApiError> {
    open_database(path)?
        .execute(
            "UPDATE knowledge_jobs SET status = 'queued', updated_at_ms = ?1
             WHERE status = 'running'",
            params![now_ms()],
        )
        .map(|_| ())
        .map_err(|error| ApiError::internal(error.to_string()))
}

fn insert_job(path: &Path, id: &str, payload: &IngestPayload) -> Result<(), ApiError> {
    let timestamp = now_ms();
    let payload_json =
        serde_json::to_string(payload).map_err(|error| ApiError::internal(error.to_string()))?;
    open_database(path)?
        .execute(
            "INSERT INTO knowledge_jobs(
                id, status, source_uri, media_type, payload_json,
                created_at_ms, updated_at_ms
             ) VALUES (?1, 'queued', ?2, ?3, ?4, ?5, ?5)",
            params![id, payload.source_uri, payload.media_type, payload_json, timestamp],
        )
        .map(|_| ())
        .map_err(|error| ApiError::internal(error.to_string()))
}

fn mark_running(path: &Path, id: &str) -> Result<(), ApiError> {
    open_database(path)?
        .execute(
            "UPDATE knowledge_jobs SET status = 'running', updated_at_ms = ?2
             WHERE id = ?1 AND status = 'queued'",
            params![id, now_ms()],
        )
        .map(|_| ())
        .map_err(|error| ApiError::internal(error.to_string()))
}

fn finish_job(
    path: &Path,
    id: &str,
    status: &str,
    error: Option<String>,
    result: Option<serde_json::Value>,
) -> Result<(), ApiError> {
    let result_json = result
        .map(|value| serde_json::to_string(&value))
        .transpose()
        .map_err(|error| ApiError::internal(error.to_string()))?;
    open_database(path)?
        .execute(
            "UPDATE knowledge_jobs
             SET status = ?2, updated_at_ms = ?3, error = ?4, result_json = ?5
             WHERE id = ?1 AND status != 'cancelled'",
            params![id, status, now_ms(), error, result_json],
        )
        .map(|_| ())
        .map_err(|error| ApiError::internal(error.to_string()))
}

fn read_payload(path: &Path, id: &str) -> Result<Option<IngestPayload>, ApiError> {
    let connection = open_database(path)?;
    let value: Option<String> = connection
        .query_row(
            "SELECT payload_json FROM knowledge_jobs WHERE id = ?1",
            params![id],
            |row| row.get(0),
        )
        .optional()
        .map_err(|error| ApiError::internal(error.to_string()))?;
    value
        .map(|json| serde_json::from_str(&json))
        .transpose()
        .map_err(|error| ApiError::internal(error.to_string()))
}

fn job_status(path: &Path, id: &str) -> Result<Option<String>, ApiError> {
    open_database(path)?
        .query_row(
            "SELECT status FROM knowledge_jobs WHERE id = ?1",
            params![id],
            |row| row.get(0),
        )
        .optional()
        .map_err(|error| ApiError::internal(error.to_string()))
}

fn queued_job_ids(path: &Path) -> Result<Vec<String>, ApiError> {
    let connection = open_database(path)?;
    let mut statement = connection
        .prepare("SELECT id FROM knowledge_jobs WHERE status = 'queued' ORDER BY created_at_ms")
        .map_err(|error| ApiError::internal(error.to_string()))?;
    statement
        .query_map([], |row| row.get(0))
        .map_err(|error| ApiError::internal(error.to_string()))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| ApiError::internal(error.to_string()))
}

fn read_job(path: &Path, id: &str) -> Result<Option<JobRecord>, ApiError> {
    open_database(path)?
        .query_row(
            "SELECT id, status, source_uri, media_type, created_at_ms,
                    updated_at_ms, error, result_json
             FROM knowledge_jobs WHERE id = ?1",
            params![id],
            row_to_job,
        )
        .optional()
        .map_err(|error| ApiError::internal(error.to_string()))
}

fn read_jobs(path: &Path) -> Result<Vec<JobRecord>, ApiError> {
    let connection = open_database(path)?;
    let mut statement = connection
        .prepare(
            "SELECT id, status, source_uri, media_type, created_at_ms,
                    updated_at_ms, error, result_json
             FROM knowledge_jobs ORDER BY created_at_ms DESC",
        )
        .map_err(|error| ApiError::internal(error.to_string()))?;
    statement
        .query_map([], row_to_job)
        .map_err(|error| ApiError::internal(error.to_string()))?
        .collect::<Result<Vec<_>, _>>()
        .map_err(|error| ApiError::internal(error.to_string()))
}

fn row_to_job(row: &rusqlite::Row<'_>) -> rusqlite::Result<JobRecord> {
    let result_json: Option<String> = row.get(7)?;
    let result = result_json.and_then(|value| serde_json::from_str(&value).ok());
    Ok(JobRecord {
        id: row.get(0)?,
        status: row.get(1)?,
        source_uri: row.get(2)?,
        media_type: row.get(3)?,
        created_at_ms: row.get(4)?,
        updated_at_ms: row.get(5)?,
        error: row.get(6)?,
        result,
    })
}

fn now_ms() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as i64
}

fn next_job_id() -> String {
    let sequence = JOB_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    format!("job-{}-{sequence}", now_ms())
}
