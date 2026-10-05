---
ovdb: 1
publish:
  - ./ovdb.yaml
  - ./ovdb-database.json
---

# OpenVaultDB publication

This repository publishes Sakila's compatibility publisher manifest and its
typed public database descriptor. The canonical database identity is
`https://demodb.dev/sakila/`; the same descriptor is served at
`https://demodb.dev/ovdb/db/sakila/ovdb-database.json`.

The SQLite fixture and static exports are published by the DemoDB site. OVDB
read and query access are available through the verified read-only mount; write
access remains disabled.
