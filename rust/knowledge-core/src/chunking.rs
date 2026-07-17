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
        assert!(overlap_chars < max_chars, "overlap must be smaller than window");
        Self { max_chars, overlap_chars }
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
            chunks.push(DocumentChunk {
                id: format!("{}:{ordinal}", document.id),
                document_id: document.id.clone(),
                ordinal,
                text,
                metadata: document.metadata.clone(),
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

    #[test]
    fn creates_overlapping_chunks() {
        let document = Document {
            id: "doc".into(), source_uri: "memory://doc".into(), media_type: "text/plain".into(),
            title: None, text: "abcdefghij".into(), metadata: BTreeMap::new(),
        };
        let chunks = FixedWindowChunker::new(6, 2).chunk(&document);
        assert_eq!(chunks.iter().map(|c| c.text.as_str()).collect::<Vec<_>>(), vec!["abcdef", "efghij"]);
    }
}
