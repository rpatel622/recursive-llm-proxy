# Catalog transfer and backup

`rlm_proxy.catalog_transfer` provides deterministic catalog export, validated import, and consistent SQLite backup operations.

Exports use format `rlm-slot-catalog`, export version `1`, and include schema and catalog version metadata. Imports validate the envelope and the complete `SlotCatalog` before atomically replacing data. An optional expected version prevents stale imports.

Database backups use SQLite's online backup API and may be created while the proxy is running. The destination must differ from the active database path. In-memory catalogs cannot be backed up by filesystem path.
