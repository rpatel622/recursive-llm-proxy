use crate::{Document, DocumentChunk};

pub trait Chunker: Send + Sync {
    fn chunk(&self, document: &Document) -> Vec<DocumentChunk>;
}

#[derive(Clone, Debug)]
pub struct FixedWindowChunker {
    max_chars: usize,
    overlap_chars: usize,
}

impl FixedWindowChunker {
    pub fn new(max_chars: usize, overlap_chars: usize) -> Self {
        assert!(max_chars > 0, "max_chars must be greater than zero");
        assert!(
            overlap_chars < max_chars,
            "overlap must be smaller than window"
        );
        Self {
            max_chars,
            overlap_chars,
        }
    }
}

impl Default for FixedWindowChunker {
    fn default() -> Self {
        Self::new(2_000, 200)
    }
}

impl Chunker for FixedWindowChunker {
    fn chunk(&self, document: &Document) -> Vec<DocumentChunk> {
        let chars: Vec<char> = document.text.chars().collect();
        if chars.is_empty() {
            return Vec::new();
        }
        let step = self.max_chars - self.overlap_chars;
        let mut chunks = Vec::new();
        let mut start = 0;
        let mut ordinal = 0;
        while start < chars.len() {
            let end = usize::min(start + self.max_chars, chars.len());
            let text: String = chars[start..end].iter().collect();
            let mut metadata = document.metadata.clone();
            metadata.insert("source_uri".into(), document.source_uri.clone());
            metadata.insert("media_type".into(), document.media_type.clone());
            if let Some(title) = &document.title {
                metadata.insert("title".into(), title.clone());
            }
            chunks.push(DocumentChunk {
                id: format!("{}:{ordinal}", document.id),
                document_id: document.id.clone(),
                ordinal,
                text,
                metadata,
            });
            if end == chars.len() {
                break;
            }
            start += step;
            ordinal += 1;
        }
        chunks
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    fn document() -> Document {
        Document {
            id: "doc".into(),
            source_uri: "memory://doc.txt".into(),
            media_type: "text/plain".into(),
            title: Some("doc.txt".into()),
            text: "abcdefghij".into(),
            metadata: BTreeMap::new(),
        }
    }

    #[test]
    fn creates_overlapping_chunks() {
        let chunks = FixedWindowChunker::new(6, 2).chunk(&document());
        assert_eq!(
            chunks
                .iter()
                .map(|chunk| chunk.text.as_str())
                .collect::<Vec<_>>(),
            vec!["abcdef", "efghij"]
        );
    }

    #[test]
    fn preserves_citation_metadata() {
        let chunks = FixedWindowChunker::new(6, 2).chunk(&document());
        let metadata = &chunks[0].metadata;

        assert_eq!(metadata.get("source_uri").map(String::as_str), Some("memory://doc.txt"));
        assert_eq!(metadata.get("media_type").map(String::as_str), Some("text/plain"));
        assert_eq!(metadata.get("title").map(String::as_str), Some("doc.txt"));
    }
}
