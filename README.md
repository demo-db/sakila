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

The `ingitdb/` directory contains 47,268 source table rows across 16 collections. It is a Git-backed, queryable snapshot prepared from the pinned SQLite fixture. Verify and query it with the installed inGitDB CLI:

```sh
ingitdb validate --path ingitdb
ingitdb select --path ingitdb --from actor_50c9c4ae --limit 1 --format json
```

[`ingitdb/export-manifest.json`](ingitdb/export-manifest.json) maps each native table to its collection, row count, original primary and foreign keys, column types, transport encodings, and SHA-256 of its record file. The source fixture SHA-256 is `9bebeee50fecb1fee115c206a4f380f2f6d1f009e7796b18b8a8cfba7c810454`. These bytes were exported against provider commit `cb9a81a8cbedcd8831737f281f888d5d584fae85`; the source fixture hash also matches this repository's pinned fixture. Record keys encode native primary keys where present; keyless tables use stable ordinal IDs, which are not native keys. Native key relationships are descriptive metadata, not enforced in this snapshot. Exact decimal values travel as strings and binary values as base64 where marked in column metadata. Source view definitions are retained as metadata only; they are not materialized in inGitDB. Source rights and original notices remain in [`data-source/`](data-source/) and [`LICENSE`](LICENSE).
