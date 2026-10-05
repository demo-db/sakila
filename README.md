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
