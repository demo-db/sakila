#!/usr/bin/env python3
"""Build the pinned MySQL Sakila 1.5 sample as a read-only SQLite fixture.

This is a deliberately bounded converter for the two checked-in upstream SQL
files, not a general MySQL migration tool. It preserves native table and view
names, row values, keys, ordinary indexes, foreign keys, and binary payloads.
MySQL procedures, functions, triggers, FULLTEXT/SPATIAL indexes, and MySQL-only
runtime behavior are documented rather than represented as SQLite features.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "data-source"
SCHEMA = SOURCE_DIR / "sakila-schema.sql"
DATA = SOURCE_DIR / "sakila-data.sql"
OUTPUT = SOURCE_DIR / "source.sqlite"
MANIFEST = ROOT / "manifest.json"
EXPECTED = {
    "sakila-schema.sql": "b32170e1e2ad5828749b61a5ec896155bcd143104b076e5ee8a3a3b013f44915",
    "sakila-data.sql": "8c228c678cec6ea9e5145ea868f48be87982252e806a547dcddb67758cadf174",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unversioned(sql: str, *, schema: bool = False) -> str:
    """Expand the upstream executable comments while dropping MySQL 8 SRID syntax."""
    sql = re.sub(r"/\*!80003\s+SRID\s+0\s*\*/", "", sql, flags=re.I)
    return re.sub(r"/\*!\d{0,5}\s*(.*?)\*/", lambda m: m.group(1), sql, flags=re.S)


def matching_paren(text: str, opening: int) -> int:
    depth = 0
    quote = None
    i = opening
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                if i + 1 < len(text) and text[i + 1] == quote:
                    i += 2
                    continue
                quote = None
        elif c in "'\"`":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unclosed parenthesized SQL expression")


def split_top_level(text: str) -> list[str]:
    values: list[str] = []
    start = depth = 0
    quote = None
    i = 0
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                if i + 1 < len(text) and text[i + 1] == quote:
                    i += 2
                    continue
                quote = None
        elif c in "'\"`":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "," and depth == 0:
            values.append(text[start:i].strip())
            start = i + 1
        i += 1
    tail = text[start:].strip()
    if tail:
        values.append(tail)
    return values


def mysql_type(sql: str) -> str:
    sql = re.sub(r"\b(?:SMALLINT|MEDIUMINT|TINYINT|BIGINT)\b", "INTEGER", sql, flags=re.I)
    sql = re.sub(r"\bINT\b", "INTEGER", sql, flags=re.I)
    sql = re.sub(r"\b(?:INT|INTEGER)\s+UNSIGNED\b", "INTEGER", sql, flags=re.I)
    sql = re.sub(r"\b(?:INTEGER|SMALLINT|MEDIUMINT|TINYINT)\s+UNSIGNED\b", "INTEGER", sql, flags=re.I)
    sql = re.sub(r"\b(?:VARCHAR|CHAR)\s*\(\s*\d+\s*\)", "TEXT", sql, flags=re.I)
    sql = re.sub(r"\b(?:DATETIME|TIMESTAMP|YEAR)\b", "TEXT", sql, flags=re.I)
    sql = re.sub(r"\b(?:DECIMAL|NUMERIC)\s*\(\s*\d+\s*,\s*\d+\s*\)", "NUMERIC", sql, flags=re.I)
    sql = re.sub(r"\b(?:ENUM|SET)\s*\([^)]*\)", "TEXT", sql, flags=re.I)
    sql = re.sub(r"\bGEOMETRY\b", "BLOB", sql, flags=re.I)
    sql = re.sub(r"\b(?:TINYTEXT|MEDIUMTEXT|LONGTEXT)\b", "TEXT", sql, flags=re.I)
    sql = re.sub(r"\b(?:TINYBLOB|MEDIUMBLOB|LONGBLOB)\b", "BLOB", sql, flags=re.I)
    sql = re.sub(r"\bBOOL(?:EAN)?\b", "INTEGER", sql, flags=re.I)
    sql = re.sub(r"\s+CHARACTER\s+SET\s+\w+", "", sql, flags=re.I)
    sql = re.sub(r"\s+COLLATE\s+\w+", "", sql, flags=re.I)
    sql = re.sub(r"\s+ON\s+UPDATE\s+CURRENT_TIMESTAMP(?:\(\))?", "", sql, flags=re.I)
    sql = re.sub(r"\bAUTO_INCREMENT\b", "AUTOINCREMENT", sql, flags=re.I)
    return sql


def create_tables(db: sqlite3.Connection, sql: str) -> tuple[list[str], list[str]]:
    sql = unversioned(sql)
    sql = re.sub(r"(?m)^\s*--.*$", "", sql)
    tables: list[str] = []
    index_statements: list[str] = []
    pattern = re.compile(r"CREATE\s+TABLE\s+`?(\w+)`?\s*\(", re.I)
    for match in pattern.finditer(sql):
        name = match.group(1)
        end = matching_paren(sql, match.end() - 1)
        definitions = []
        raw_items = split_top_level(sql[match.end():end])
        auto_columns = {
            re.match(r"`?(\w+)`?", item).group(1)
            for item in raw_items
            if re.search(r"\bAUTO_INCREMENT\b", item, re.I)
            and re.match(r"`?(\w+)`?", item)
        }
        for item in raw_items:
            item = item.strip()
            if not item or item.startswith("--"):
                continue
            if re.match(r"(?:FULLTEXT|SPATIAL)\s+KEY\b", item, re.I):
                continue
            key = re.match(r"(?:UNIQUE\s+)?KEY\s*(\w+)?\s*\((.*)\)\s*$", item, re.I | re.S)
            if key:
                unique = item.upper().startswith("UNIQUE")
                cols = ", ".join('"' + c.strip().strip('`') + '"' for c in split_top_level(key.group(2)))
                idx = f"{name}_{key.group(1)}" if key.group(1) else f"uq_{name}_{len(index_statements)}"
                index_statements.append(f'CREATE {"UNIQUE " if unique else ""}INDEX "{idx}" ON "{name}" ({cols})')
                continue
            # FULLTEXT and ordinary indexes are not table constraints; all
            # native key declarations that remain are PK, FK, or UNIQUE.
            item = re.sub(r"^CONSTRAINT\s+`?\w+`?\s+", "", item, flags=re.I)
            item = re.sub(r"\bUNSIGNED\b", "", item, flags=re.I)
            item = re.sub(r"\bAUTO_INCREMENT\b", "AUTOINCREMENT", item, flags=re.I)
            item = re.sub(r"\s+ON\s+UPDATE\s+CURRENT_TIMESTAMP(?:\(\))?", "", item, flags=re.I)
            item = re.sub(r"\s+CHARACTER\s+SET\s+\w+", "", item, flags=re.I)
            item = re.sub(r"\s+COLLATE\s+\w+", "", item, flags=re.I)
            item = mysql_type(item)
            item = item.replace("`", '"')
            # SQLite AUTOINCREMENT is valid only on INTEGER PRIMARY KEY.
            item = re.sub(r"\bINTEGER\s+NOT\s+NULL\s+AUTOINCREMENT\b", "INTEGER PRIMARY KEY AUTOINCREMENT", item, flags=re.I)
            item = re.sub(r"\bINTEGER\s+AUTOINCREMENT\b", "INTEGER PRIMARY KEY AUTOINCREMENT", item, flags=re.I)
            item = re.sub(r"\bPRIMARY\s+KEY\s*\(([^)]*)\)", lambda m: "PRIMARY KEY (" + m.group(1).replace("`", '"') + ")", item, flags=re.I)
            primary = re.fullmatch(r'PRIMARY\s+KEY\s*\(\s*"?(\w+)"?\s*\)', item, flags=re.I)
            if primary and primary.group(1) in auto_columns:
                # MySQL AUTO_INCREMENT translates to SQLite's rowid alias.
                # Its PK is already inlined to satisfy SQLite's AUTOINCREMENT rule.
                continue
            item = re.sub(r"\bFOREIGN\s+KEY\s*\(([^)]*)\)\s+REFERENCES\s+`?(\w+)`?\s*\(([^)]*)\)", lambda m: f'FOREIGN KEY ({m.group(1).replace("`", chr(34))}) REFERENCES "{m.group(2)}" ({m.group(3).replace("`", chr(34))})', item, flags=re.I)
            item = re.sub(r"\bDEFAULT\s+TRUE\b", "DEFAULT 1", item, flags=re.I)
            item = re.sub(r"\bDEFAULT\s+FALSE\b", "DEFAULT 0", item, flags=re.I)
            definitions.append(" ".join(item.split()))
        create_sql = f'CREATE TABLE "{name}" ({", ".join(definitions)})'
        try:
            db.execute(create_sql)
        except sqlite3.Error as exc:
            raise ValueError(f"failed creating {name}: {create_sql}: {exc}") from exc
        tables.append(name)
    if not tables:
        raise ValueError("no CREATE TABLE statements found")
    for statement in index_statements:
        db.execute(statement)
    return tables, index_statements


def sql_statements(source: str):
    start = 0
    quote = None
    i = 0
    while i < len(source):
        c = source[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                if i + 1 < len(source) and source[i + 1] == quote:
                    i += 2
                    continue
                quote = None
        elif c in "'\"`":
            quote = c
        elif c == ";":
            yield source[start:i].strip()
            start = i + 1
        i += 1


def transform_insert(statement: str) -> str:
    statement = re.sub(r"/\*!\d{0,5}\s*(.*?)\*/", lambda m: m.group(1), statement, flags=re.S)
    statement = re.sub(r"\bINSERT\s+INTO\s+`?(\w+)`?", lambda m: f'INSERT INTO "{m.group(1)}"', statement, flags=re.I)
    statement = statement.replace("`", '"')
    statement = re.sub(r"\b0x([0-9a-f]+)\b", lambda m: "X'" + m.group(1) + "'", statement, flags=re.I)
    statement = re.sub(r"\bTRUE\b", "1", statement, flags=re.I)
    statement = re.sub(r"\bFALSE\b", "0", statement, flags=re.I)
    return statement


def rewrite_views(sql: str) -> list[tuple[str, str]]:
    sql = unversioned(sql)
    result = []
    pattern = re.compile(r"CREATE\s+(?:DEFINER\s*=\s*[^\s]+\s+SQL\s+SECURITY\s+\w+\s+)?VIEW\s+`?(\w+)`?\s+AS\s+(.*?);", re.I | re.S)
    for match in pattern.finditer(sql):
        name, body = match.groups()
        if name == "actor_info":
            # The upstream view uses ordered, nested GROUP_CONCAT syntax which
            # SQLite does not implement. Preserve its output with ordered
            # subqueries and SQLite's built-in aggregate instead.
            body = '''
                SELECT a.actor_id, a.first_name, a.last_name,
                  (SELECT group_concat(category_info, '; ') FROM (
                    SELECT c.name || ': ' ||
                      (SELECT group_concat(title, ', ') FROM (
                        SELECT f.title
                        FROM film AS f
                        JOIN film_category AS fc ON f.film_id = fc.film_id
                        JOIN film_actor AS fa ON f.film_id = fa.film_id
                        WHERE fc.category_id = c.category_id AND fa.actor_id = a.actor_id
                        ORDER BY f.title
                      )) AS category_info
                    FROM category AS c
                    JOIN film_category AS fc ON c.category_id = fc.category_id
                    JOIN film_actor AS fa ON fc.film_id = fa.film_id
                    WHERE fa.actor_id = a.actor_id
                    GROUP BY c.category_id, c.name
                    ORDER BY c.name
                  )) AS film_info
                FROM actor AS a
            '''
            result.append((name, " ".join(body.split())))
            continue
        body = re.sub(r"_utf8mb4(?=')", "", body, flags=re.I)
        body = body.replace("`", '"')
        body = re.sub(
            r"\bIF\s*\(\s*cu\.active\s*,\s*'active'\s*,\s*''\s*\)",
            "CASE WHEN cu.active THEN 'active' ELSE '' END",
            body,
            flags=re.I,
        )
        body = re.sub(r"\bUCASE\s*\(", "upper(", body, flags=re.I)
        body = re.sub(r"\bLCASE\s*\(", "lower(", body, flags=re.I)
        # Rewrite MySQL's GROUP_CONCAT(expr SEPARATOR sep) form to SQLite's
        # two-argument aggregate while respecting nested calls and literals.
        pos = 0
        chunks = []
        token = re.compile(r"GROUP_CONCAT\s*\(", re.I)
        while m := token.search(body, pos):
            chunks.append(body[pos:m.start()])
            opening = m.end() - 1
            close = matching_paren(body, opening)
            args = body[opening + 1:close]
            sep_at = re.search(r"\s+SEPARATOR\s+", args, flags=re.I)
            if sep_at:
                expr = args[:sep_at.start()].strip()
                sep = args[sep_at.end():].strip()
                chunks.append(f"group_concat({expr}, {sep})")
            else:
                chunks.append("group_concat(" + args + ")")
            pos = close + 1
        chunks.append(body[pos:])
        body = "".join(chunks)
        body = rewrite_concat(body)
        result.append((name, " ".join(body.split())))
    return result


def rewrite_concat(sql: str) -> str:
    """Replace MySQL CONCAT calls with SQLite's portable concatenation operator."""
    token = re.compile(r"\bCONCAT\s*\(", re.I)
    output = []
    pos = 0
    while match := token.search(sql, pos):
        output.append(sql[pos:match.start()])
        opening = match.end() - 1
        closing = matching_paren(sql, opening)
        args = split_top_level(sql[opening + 1:closing])
        if not args:
            raise ValueError("empty MySQL CONCAT call in source view")
        output.append("(" + " || ".join(rewrite_concat(arg) for arg in args) + ")")
        pos = closing + 1
    output.append(sql[pos:])
    return "".join(output)


def build_database(output: Path) -> None:
    for path in (SCHEMA, DATA):
        expected = EXPECTED[path.name]
        actual = digest(path)
        if actual != expected:
            raise ValueError(f"pinned source hash mismatch for {path.name}: {actual}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    schema = SCHEMA.read_text(encoding="utf-8")
    data = DATA.read_text(encoding="utf-8")
    db = sqlite3.connect(output)
    db.execute("PRAGMA foreign_keys=OFF")
    tables, indexes = create_tables(db, schema)
    insert_count = 0
    for statement in sql_statements(data):
        if re.match(r"INSERT\s+INTO\b", statement, re.I):
            converted = transform_insert(statement)
            try:
                db.execute(converted)
            except sqlite3.Error as exc:
                raise ValueError(f"failed importing {converted[:90]!r}: {exc}") from exc
            insert_count += 1
    # The upstream ins_film trigger mirrors each film row into film_text.
    # The published seed script installs that trigger before the data load but
    # does not insert film_text directly; reproduce its initial effect once.
    db.execute("INSERT INTO film_text (film_id, title, description) SELECT film_id, title, description FROM film")
    for name, query in rewrite_views(schema):
        db.execute(f'CREATE VIEW "{name}" AS {query}')
    db.commit()
    db.execute("PRAGMA foreign_keys=ON")
    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("SQLite integrity check failed")
    fk_errors = db.execute("PRAGMA foreign_key_check").fetchall()
    if fk_errors:
        raise ValueError(f"foreign-key violations: {fk_errors[:5]}")
    view_names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='view' ORDER BY name")]
    expected_views = {
        "actor_info", "customer_list", "film_list", "nicer_but_slower_film_list",
        "staff_list", "sales_by_store", "sales_by_film_category",
    }
    if set(view_names) != expected_views:
        raise ValueError(f"source view set changed: {view_names}")
    if db.execute("SELECT COUNT(*) FROM actor_info").fetchone()[0] != 200:
        raise ValueError("actor_info must include every actor, including actors without films")
    for name in view_names:
        try:
            db.execute(f'SELECT * FROM "{name}" LIMIT 1').fetchall()
        except sqlite3.Error as exc:
            raise ValueError(f"converted view {name} cannot execute: {exc}") from exc
    if not tables or insert_count == 0:
        raise ValueError("fixture contains no source tables or inserts")
    expected_rows = {
        "actor": 200, "address": 603, "category": 16, "city": 600,
        "country": 109, "customer": 599, "film": 1000, "film_actor": 5462,
        "film_category": 1000, "film_text": 1000, "inventory": 4581,
        "language": 6, "payment": 16044, "rental": 16044, "staff": 2, "store": 2,
    }
    if set(tables) != set(expected_rows):
        raise ValueError(f"source table set changed: {sorted(tables)}")
    if insert_count != 17:
        raise ValueError(f"expected 17 source insert statements, got {insert_count}")
    for table, expected in expected_rows.items():
        actual = db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        if actual != expected:
            raise ValueError(f"{table}: expected {expected} rows, got {actual}")
    if db.execute("SELECT COUNT(*) FROM staff WHERE picture IS NOT NULL").fetchone()[0] != 1:
        raise ValueError("expected the source's non-null staff picture BLOB")
    if db.execute("SELECT COUNT(*) FROM staff WHERE hex(substr(picture,1,8))='89504E470D0A1A0A'").fetchone()[0] != 1:
        raise ValueError("staff picture PNG bytes were not preserved")
    if db.execute("SELECT COUNT(*) FROM address WHERE typeof(location)='blob'").fetchone()[0] != 603:
        raise ValueError("address geometry WKB values were not preserved as BLOBs")
    db.execute("VACUUM")
    db.close()
    print(f"Built Sakila SQLite: {len(tables)} tables, {len(view_names)} views, {insert_count} insert statements, {output.stat().st_size} bytes")


def sqlite_snapshot(path: Path) -> dict[str, object]:
    """Capture logical schema and all values independent of SQLite file headers."""
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        objects = db.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        table_names = [row[1] for row in objects if row[0] == "table"]
        view_names = [row[1] for row in objects if row[0] == "view"]

        def encode(value):
            if isinstance(value, bytes):
                return ["blob", value.hex()]
            if value is None:
                return ["null"]
            if isinstance(value, int):
                return ["integer", value]
            if isinstance(value, float):
                return ["real", value.hex()]
            return ["text", value]

        def rows(name):
            values = [[encode(value) for value in row] for row in db.execute(f'SELECT * FROM "{name}"')]
            return sorted(values, key=lambda row: json.dumps(row, ensure_ascii=False, separators=(",", ":")))

        tables = {}
        for table in table_names:
            indexes = []
            for index in db.execute(f'PRAGMA index_list("{table}")').fetchall():
                indexes.append((index, db.execute(f'PRAGMA index_xinfo("{index[1]}")').fetchall()))
            tables[table] = {
                "columns": db.execute(f'PRAGMA table_xinfo("{table}")').fetchall(),
                "foreignKeys": db.execute(f'PRAGMA foreign_key_list("{table}")').fetchall(),
                "indexes": indexes,
                "rows": rows(table),
            }
        return {"objects": objects, "tables": tables, "views": {view: rows(view) for view in view_names}}
    finally:
        db.close()


def build() -> None:
    build_database(OUTPUT)
    manifest = json.loads(MANIFEST.read_text())
    manifest["source"]["databaseSha256"] = digest(OUTPUT)
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"SQLite SHA-256: {digest(OUTPUT)}")


def check_rebuild() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected_hash = manifest["source"]["databaseSha256"]
    actual_hash = digest(OUTPUT)
    if actual_hash != expected_hash:
        raise ValueError(f"checked-in SQLite artifact SHA-256 mismatch: expected {expected_hash}, got {actual_hash}")
    with tempfile.TemporaryDirectory(prefix="sakila-source-check-") as temp_dir:
        rebuilt = Path(temp_dir) / "rebuilt.sqlite"
        build_database(rebuilt)
        if sqlite_snapshot(OUTPUT) != sqlite_snapshot(rebuilt):
            raise ValueError("rebuilt fixture differs logically from source.sqlite (schema, constraints, indexes, views, rows, or BLOBs)")
    print(f"Verified checked-in SQLite artifact {expected_hash} and full logical rebuild equivalence")


if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        check_rebuild()
    elif sys.argv[1:]:
        raise SystemExit("usage: rebuild-source.py [--check]")
    else:
        build()
