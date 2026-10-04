# Sakila source provenance

This fixture is derived from the official MySQL Sakila 1.5 archive at
<https://downloads.mysql.com/docs/sakila-db.zip>. The downloaded archive had
SHA-256 `ef4ab9aab7a433311eff6558561bf47de231fe9f6d49f03de67e593418df719c`.
The retained source files are `sakila-schema.sql` (SHA-256
`b32170e1e2ad5828749b61a5ec896155bcd143104b076e5ee8a3a3b013f44915`) and
`sakila-data.sql` (SHA-256
`8c228c678cec6ea9e5145ea868f48be87982252e806a547dcddb67758cadf174`). Each
source file contains the upstream New BSD license and copyright notice.

The archive's Workbench model and documentation are excluded because the
MySQL sample license covers the schema and data SQL files only. The fixture
builder expands the source's versioned geometry clauses, imports every source
row, and retains raw address WKB and staff-picture PNG bytes as SQLite BLOBs.
It populates `film_text` as the upstream `ins_film` trigger does during a fresh
installation. All seven source views are translated to executable SQLite views;
`actor_info` uses ordered subqueries because SQLite lacks MySQL's ordered
`GROUP_CONCAT` syntax.

The SQLite fixture does not emulate MySQL stored procedures, functions,
triggers after import, FULLTEXT or SPATIAL indexes, collation rules, ENUM/SET
constraints, or automatic `ON UPDATE` timestamp behavior. Geometry remains
raw WKB without spatial decoding. `scripts/rebuild-source.py --check` verifies
both pinned SQL hashes and the complete logical schema, index, view, value,
and BLOB contents of the checked-in fixture.
