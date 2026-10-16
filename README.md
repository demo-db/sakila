# Sakila

Sakila is MySQL's sample video-rental database, published here as a
reproducible SQLite fixture with portable table exports and pinned
ModelSpec/MeaningGraph metadata. Explore it at <https://sakila.demodb.dev/>.

The fixture contains 16 native tables and seven executable views. Its 16,044
rentals and payments, 5,462 film-actor relationships, 603 addresses, film
catalogue, inventory, and the source's non-null staff image remain available in
full. Address geometry and the staff picture are stored as BLOBs; generated JSON and CSV encode
those bytes as base64. The source is Sakila 1.5, distributed by MySQL under its
New BSD license. The download, archive digest, SQL file digests, license scope,
and conversion limits are documented in [`data-source/README.md`](data-source/README.md).

To rebuild and validate the source fixture:

```sh
python3 scripts/rebuild-source.py
python3 scripts/rebuild-source.py --check
```

Provider exports, ModelSpec, MeaningGraph, the OVDB descriptor, and checksum
records are generated from `manifest.json` and `data-source/source.sqlite` by
the immutable shared generator used in CI. Run the generator and validation
workflow before changing generated files. The verified read-only OVDB mount provides record lookups and query access;
writes remain disabled.

## Native inGitDB snapshot

The `ingitdb/` directory contains 47,268 source rows in 16 collections, exported from the pinned SQLite fixture by DataTug's generic DALgo → inGitDB exporter. The source fixture SHA-256 is `9bebeee50fecb1fee115c206a4f380f2f6d1f009e7796b18b8a8cfba7c810454`. This Git-backed edition is a queryable snapshot, not a live SQL database.

Use DataTug CLI v0.61.1 or newer to reproduce this export, and inGitDB CLI v0.70.0 or newer to validate and query this edition.

```sh
ingitdb validate --path ingitdb
ingitdb select --path ingitdb --from 'actor' --limit 1 --format json
```

Each source table has a `.collection/definition.yaml` with ordered fields, source primary-key columns, portable indexes and foreign-key groups/actions. `.ingitdb/source-collections.json` maps native collection IDs to exact SQLite table names; names outside inGitDB’s ID alphabet use a deterministic `dt_` UTF-8 hex ID. Its `source_schema.source_definition_json` retains the original SQLite DDL, declared column types, defaults and complete index details. The native record file is `records.json`, keyed by deterministic transport IDs derived from the ordered source primary key; keyless tables use source-row ordinals. These transport IDs are not new SQL columns. Exact decimals are stored as strings, BLOBs as base64, and `source-storage-*.jsonl` sidecars retain decimal SQLite storage classes where needed. The 7 source view definitions remain in `.ingitdb/source-views.yaml` as metadata; they are not materialized collections.

The checked-in Git snapshot is the published inGitDB edition. [`ingitdb/export-manifest.json`](ingitdb/export-manifest.json) records the DataTug version, binary hash, pinned source and record checksums, plus the independent parity receipt at [`ingitdb/native-parity-report.json`](ingitdb/native-parity-report.json). Its `prepared-not-hosted` status describes the generated bundle before repository publication and also covers BigQuery load files; it does not imply a hosted BigQuery service.

The published record format is DataTug's default JSON. To produce another edition from a verified, decoded copy of this pinned SQLite fixture, choose a **new** destination and pass `--records-format json` (default), `jsonl`, `ingr`, `csv`, or `yaml`:

```sh
datatug db export --from sqlite:///absolute/path/to/pinned-source.sqlite \
  --to ingitdb:///absolute/path/to/new-output --records-format json
```

The independent checker in `demo-db/websites/scripts/hosting-tools/validate_datatug_exports.py` compares the native schema and every typed row at its transport ID with this repository's pinned source. Run it from a checkout containing both repositories:

```sh
python3 ../websites/scripts/hosting-tools/validate_datatug_exports.py . ingitdb \
  --report /private/tmp/sakila-ingitdb-parity.json
```

The source primary keys, foreign keys, UNIQUE and CHECK constraints, defaults, collations and SQL actions are preserved as source metadata; inGitDB does not enforce their full SQL behavior on later record edits. Source rights and original notices remain in [`data-source/`](data-source/) and [`LICENSE`](LICENSE).

## MySQL script (`dialect-scripts/`)

`dialect-scripts/sakila.mysql.sql` is a MySQL 8 script that creates and fills this database. It is written by the DataTug SQL-script exporter
(`datatug db copy --to sqlscript:///<file>?dialect=mysql`, release v0.97.1, pinned by SHA-256 in `demo-db/websites` `config/dialect-scripts.json`) from the pinned
SQLite fixture, loaded into a real MySQL 8.4 and compared with the fixture. It is labelled "DemoDB contract edition, identical to the SQLite/CSV/JSON": the same tables and
rows, with everything MySQL cannot carry exactly (for example views) listed in the script header and in `dialect-scripts/sakila.mysql.report.json`.
`dialect-scripts/manifest.json` records the inputs (the SQLite SHA-256, the exporter pin, the label, the licence from `manifest.json` and the attribution below), the stored and
decoded SHA-256, and the verification run. Nothing else in this repository changes: the files are outside `artifacts/`, so the contract, the checksums and the model are untouched.

```sh
mysql --default-character-set=utf8mb4 --skip-commands --skip-system-command --database <empty database> < dialect-scripts/sakila.mysql.sql
node websites/scripts/dialect-scripts.mjs check --provider .   # no datatug binary and no Docker needed
```

The licence (BSD-3-Clause) and this attribution are in the script header: Sakila sample database 1.5, Copyright (c) 2006, 2026, Oracle and/or its affiliates, New BSD licence (BSD-3-Clause), https://downloads.mysql.com/docs/sakila-db.zip
