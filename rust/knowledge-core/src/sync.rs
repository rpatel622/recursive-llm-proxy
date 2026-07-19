use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SourceFingerprint {
    pub source_uri: String,
    pub content_hash: String,
    pub size_bytes: u64,
    pub modified_unix_ms: Option<u64>,
}

impl SourceFingerprint {
    pub fn from_bytes(
        source_uri: impl Into<String>,
        bytes: &[u8],
        modified_unix_ms: Option<u64>,
    ) -> Self {
        Self {
            source_uri: source_uri.into(),
            content_hash: fnv1a_hex(bytes),
            size_bytes: bytes.len() as u64,
            modified_unix_ms,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SyncAction {
    Create,
    Update,
    Unchanged,
    Delete,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SyncEntry {
    pub source_uri: String,
    pub action: SyncAction,
}

#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct SyncManifest {
    entries: BTreeMap<String, SourceFingerprint>,
}

impl SyncManifest {
    pub fn from_sources(sources: impl IntoIterator<Item = SourceFingerprint>) -> Self {
        Self {
            entries: sources
                .into_iter()
                .map(|source| (source.source_uri.clone(), source))
                .collect(),
        }
    }

    pub fn get(&self, source_uri: &str) -> Option<&SourceFingerprint> {
        self.entries.get(source_uri)
    }

    pub fn len(&self) -> usize {
        self.entries.len()
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    pub fn plan(&self, observed: &SyncManifest) -> Vec<SyncEntry> {
        let mut source_uris: BTreeSet<String> = self.entries.keys().cloned().collect();
        source_uris.extend(observed.entries.keys().cloned());
        source_uris
            .into_iter()
            .map(|source_uri| {
                let action = match (self.entries.get(&source_uri), observed.entries.get(&source_uri)) {
                    (None, Some(_)) => SyncAction::Create,
                    (Some(_), None) => SyncAction::Delete,
                    (Some(previous), Some(current)) if previous == current => SyncAction::Unchanged,
                    (Some(_), Some(_)) => SyncAction::Update,
                    (None, None) => unreachable!("source URI came from neither manifest"),
                };
                SyncEntry { source_uri, action }
            })
            .collect()
    }
}

fn fnv1a_hex(bytes: &[u8]) -> String {
    let mut hash = 0xcbf29ce484222325_u64;
    for byte in bytes {
        hash ^= u64::from(*byte);
        hash = hash.wrapping_mul(0x100000001b3);
    }
    format!("{hash:016x}")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn source(uri: &str, content: &[u8]) -> SourceFingerprint {
        SourceFingerprint::from_bytes(uri, content, Some(1))
    }

    #[test]
    fn fingerprints_are_deterministic_and_content_sensitive() {
        assert_eq!(source("file:///a", b"alpha"), source("file:///a", b"alpha"));
        assert_ne!(source("file:///a", b"alpha"), source("file:///a", b"beta"));
    }

    #[test]
    fn plans_create_update_unchanged_and_delete() {
        let previous = SyncManifest::from_sources([
            source("file:///delete", b"old"),
            source("file:///same", b"same"),
            source("file:///update", b"old"),
        ]);
        let observed = SyncManifest::from_sources([
            source("file:///create", b"new"),
            source("file:///same", b"same"),
            source("file:///update", b"new"),
        ]);
        let plan = previous.plan(&observed);
        assert_eq!(
            plan,
            vec![
                SyncEntry {
                    source_uri: "file:///create".into(),
                    action: SyncAction::Create,
                },
                SyncEntry {
                    source_uri: "file:///delete".into(),
                    action: SyncAction::Delete,
                },
                SyncEntry {
                    source_uri: "file:///same".into(),
                    action: SyncAction::Unchanged,
                },
                SyncEntry {
                    source_uri: "file:///update".into(),
                    action: SyncAction::Update,
                },
            ]
        );
    }
}
