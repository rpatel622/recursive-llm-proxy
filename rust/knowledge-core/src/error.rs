use thiserror::Error;

#[derive(Debug, Error)]
pub enum KnowledgeError {
    #[error("document extraction failed: {0}")]
    Extraction(String),
    #[error("embedding failed: {0}")]
    Embedding(String),
    #[error("storage failed: {0}")]
    Storage(String),
    #[error("invalid configuration: {0}")]
    Configuration(String),
}

pub type Result<T> = std::result::Result<T, KnowledgeError>;
