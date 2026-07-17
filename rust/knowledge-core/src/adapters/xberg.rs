use std::collections::BTreeMap;

use async_trait::async_trait;
use xberg::{extract, ExtractInput, ExtractionConfig};

use crate::{Document, DocumentExtractor, KnowledgeError, Result};

const DEFAULT_MAX_INPUT_BYTES: usize = 64 * 1024 * 1024;
const DEFAULT_MAX_OUTPUT_CHARS: usize = 8 * 1024 * 1024;

const SUPPORTED_MEDIA_TYPES: &[&str] = &[
    "text/plain",
    "text/markdown",
    "text/html",
    "application/xhtml+xml",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
];

#[derive(Clone, Debug)]
pub struct XbergDocumentExtractor {
    max_input_bytes: usize,
    max_output_chars: usize,
}

impl XbergDocumentExtractor {
    #[must_use]
    pub fn new(max_input_bytes: usize, max_output_chars: usize) -> Self {
        assert!(
            max_input_bytes > 0,
            "max_input_bytes must be greater than zero"
        );
        assert!(
            max_output_chars > 0,
            "max_output_chars must be greater than zero"
        );
        Self {
            max_input_bytes,
            max_output_chars,
        }
    }

    fn validate(&self, media_type: &str, bytes: &[u8]) -> Result<()> {
        if bytes.is_empty() {
            return Err(KnowledgeError::Extraction("document is empty".into()));
        }
        if bytes.len() > self.max_input_bytes {
            return Err(KnowledgeError::Extraction(format!(
                "document is {} bytes; maximum is {} bytes",
                bytes.len(),
                self.max_input_bytes
            )));
        }
        if !SUPPORTED_MEDIA_TYPES.contains(&media_type) {
            return Err(KnowledgeError::Extraction(format!(
                "unsupported media type: {media_type}"
            )));
        }
        Ok(())
    }
}

impl Default for XbergDocumentExtractor {
    fn default() -> Self {
        Self::new(DEFAULT_MAX_INPUT_BYTES, DEFAULT_MAX_OUTPUT_CHARS)
    }
}

#[async_trait]
impl DocumentExtractor for XbergDocumentExtractor {
    async fn extract(
        &self,
        source_uri: &str,
        media_type: &str,
        bytes: &[u8],
    ) -> Result<Document> {
        self.validate(media_type, bytes)?;

        let filename = filename_hint(source_uri);
        let input = ExtractInput::from_bytes(bytes.to_vec(), media_type, filename.clone());
        let output = extract(input, &ExtractionConfig::default())
            .await
            .map_err(|error| KnowledgeError::Extraction(error.to_string()))?;

        if let Some(error) = output.errors.first() {
            return Err(KnowledgeError::Extraction(error.message.clone()));
        }

        let extracted = output.results.into_iter().next().ok_or_else(|| {
            KnowledgeError::Extraction("Xberg returned no extracted document".into())
        })?;
        let text = truncate_chars(extracted.content.trim(), self.max_output_chars);
        if text.is_empty() {
            return Err(KnowledgeError::Extraction(
                "document contains no extractable text".into(),
            ));
        }

        let mut metadata = BTreeMap::new();
        metadata.insert("extractor".into(), "xberg".into());
        metadata.insert("source_media_type".into(), media_type.into());
        if text.chars().count() == self.max_output_chars
            && extracted.content.trim().chars().count() > self.max_output_chars
        {
            metadata.insert("truncated".into(), "true".into());
        }

        Ok(Document {
            id: stable_document_id(source_uri, &text),
            source_uri: source_uri.into(),
            media_type: media_type.into(),
            title: filename,
            text,
            metadata,
        })
    }
}

fn filename_hint(source_uri: &str) -> Option<String> {
    source_uri
        .rsplit(['/', '\\'])
        .find(|part| !part.is_empty())
        .map(ToOwned::to_owned)
}

fn truncate_chars(value: &str, limit: usize) -> String {
    value.chars().take(limit).collect()
}

fn stable_document_id(source_uri: &str, text: &str) -> String {
    let mut hash = 0xcbf2_9ce4_8422_2325_u64;
    for byte in source_uri.bytes().chain([0]).chain(text.bytes()) {
        hash ^= u64::from(byte);
        hash = hash.wrapping_mul(0x0000_0100_0000_01b3);
    }
    format!("doc-{hash:016x}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn extracts_plain_text() {
        let extractor = XbergDocumentExtractor::default();
        let document = extractor
            .extract(
                "memory://notes/example.txt",
                "text/plain",
                b"Hello from Xberg",
            )
            .await
            .unwrap();

        assert_eq!(document.text, "Hello from Xberg");
        assert_eq!(document.title.as_deref(), Some("example.txt"));
        assert_eq!(
            document.metadata.get("extractor").map(String::as_str),
            Some("xberg")
        );
    }

    #[tokio::test]
    async fn extracts_html_text() {
        let extractor = XbergDocumentExtractor::default();
        let document = extractor
            .extract(
                "memory://page.html",
                "text/html",
                b"<html><body><h1>Title</h1><p>Useful text</p></body></html>",
            )
            .await
            .unwrap();

        assert!(document.text.contains("Title"));
        assert!(document.text.contains("Useful text"));
    }

    #[tokio::test]
    async fn rejects_unsupported_media_type() {
        let extractor = XbergDocumentExtractor::default();
        let error = extractor
            .extract("memory://image.png", "image/png", b"not-an-image")
            .await
            .unwrap_err();

        assert!(error.to_string().contains("unsupported media type"));
    }

    #[tokio::test]
    async fn enforces_input_limit() {
        let extractor = XbergDocumentExtractor::new(4, 100);
        let error = extractor
            .extract("memory://large.txt", "text/plain", b"12345")
            .await
            .unwrap_err();

        assert!(error.to_string().contains("maximum is 4 bytes"));
    }

    #[tokio::test]
    async fn truncates_large_output() {
        let extractor = XbergDocumentExtractor::new(100, 5);
        let document = extractor
            .extract("memory://short.txt", "text/plain", b"abcdefgh")
            .await
            .unwrap();

        assert_eq!(document.text, "abcde");
        assert_eq!(
            document.metadata.get("truncated").map(String::as_str),
            Some("true")
        );
    }

    #[test]
    fn ids_are_deterministic_and_content_sensitive() {
        assert_eq!(
            stable_document_id("memory://a", "same"),
            stable_document_id("memory://a", "same")
        );
        assert_ne!(
            stable_document_id("memory://a", "same"),
            stable_document_id("memory://a", "different")
        );
    }
}
