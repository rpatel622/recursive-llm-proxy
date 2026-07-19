use std::collections::HashMap;
use std::sync::Mutex;

use async_trait::async_trait;

use crate::{Embedder, Result};

pub struct CachingEmbedder<E> {
    inner: E,
    cache: Mutex<HashMap<String, Vec<f32>>>,
}

impl<E> CachingEmbedder<E> {
    pub fn new(inner: E) -> Self {
        Self {
            inner,
            cache: Mutex::new(HashMap::new()),
        }
    }

    pub fn len(&self) -> usize {
        self.cache.lock().expect("embedding cache poisoned").len()
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    pub fn clear(&self) {
        self.cache
            .lock()
            .expect("embedding cache poisoned")
            .clear();
    }
}

#[async_trait]
impl<E> Embedder for CachingEmbedder<E>
where
    E: Embedder,
{
    async fn embed(&self, texts: &[String]) -> Result<Vec<Vec<f32>>> {
        if texts.is_empty() {
            return Ok(Vec::new());
        }

        let missing = {
            let cache = self.cache.lock().expect("embedding cache poisoned");
            let mut unique = Vec::new();
            for text in texts {
                if !cache.contains_key(text) && !unique.contains(text) {
                    unique.push(text.clone());
                }
            }
            unique
        };

        if !missing.is_empty() {
            let vectors = self.inner.embed(&missing).await?;
            if vectors.len() != missing.len() {
                return Err(crate::KnowledgeError::Embedding(format!(
                    "embedder returned {} vectors for {} cache misses",
                    vectors.len(),
                    missing.len()
                )));
            }
            let mut cache = self.cache.lock().expect("embedding cache poisoned");
            for (text, vector) in missing.into_iter().zip(vectors) {
                cache.insert(text, vector);
            }
        }

        let cache = self.cache.lock().expect("embedding cache poisoned");
        Ok(texts
            .iter()
            .map(|text| cache.get(text).expect("cache miss after fill").clone())
            .collect())
    }
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicUsize, Ordering};

    use super::*;

    struct CountingEmbedder {
        calls: AtomicUsize,
    }

    #[async_trait]
    impl Embedder for CountingEmbedder {
        async fn embed(&self, texts: &[String]) -> Result<Vec<Vec<f32>>> {
            self.calls.fetch_add(1, Ordering::SeqCst);
            Ok(texts
                .iter()
                .map(|text| vec![text.len() as f32])
                .collect())
        }
    }

    #[tokio::test]
    async fn caches_duplicate_and_repeated_texts() {
        let embedder = CachingEmbedder::new(CountingEmbedder {
            calls: AtomicUsize::new(0),
        });
        let first = embedder
            .embed(&["alpha".into(), "alpha".into(), "beta".into()])
            .await
            .unwrap();
        let second = embedder.embed(&["beta".into(), "alpha".into()]).await.unwrap();

        assert_eq!(first, vec![vec![5.0], vec![5.0], vec![4.0]]);
        assert_eq!(second, vec![vec![4.0], vec![5.0]]);
        assert_eq!(embedder.inner.calls.load(Ordering::SeqCst), 1);
        assert_eq!(embedder.len(), 2);
    }

    #[tokio::test]
    async fn clear_forces_refill() {
        let embedder = CachingEmbedder::new(CountingEmbedder {
            calls: AtomicUsize::new(0),
        });
        embedder.embed(&["alpha".into()]).await.unwrap();
        embedder.clear();
        embedder.embed(&["alpha".into()]).await.unwrap();
        assert_eq!(embedder.inner.calls.load(Ordering::SeqCst), 2);
    }
}
