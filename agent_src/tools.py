"""
Retrieval tools for the FahMai agent. Read-only against the DuckDB database.

The source numeric columns are stored as text (VARCHAR). At connect time the file
is ATTACHed read-only and a typed view layer is built over the business tables in an
in-memory catalog, re-casting money columns to DECIMAL and counts to BIGINT under the
same names. The in-memory catalog is the default, so an unqualified or UPPERCASE
table/column name in a model-written query resolves to the typed view, and SUM/ORDER BY
work without a per-query CAST. RAG/embedding/metadata tables stay hidden from the schema
card but remain reachable (src-qualified) for the doc-retrieval tools.

Universal tool = run_sql over the dim_*/fact_* business tables and the doc layer
(docs_chat_messages, report_metrics, reports). claim_lookup / doc_search wrap the
rag_chunks retrieval layer; policy_resolver does as-of (SCD-2) policy resolution.
"""
import datetime as _dt
import json
import re
from decimal import Decimal

import duckdb

ID_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-]{1,}")
THAI_TOKEN = re.compile(r"[฀-๿]{2,}")

# business tables exposed through the typed view layer + schema card
_BUSINESS_PREFIXES = ("dim_", "fact_")
_BUSINESS_EXTRA = {
    "report_metrics", "reports", "docs_chat_messages",
    "docs_key_value_blocks", "docs_markdown_tables",
    "pos_transactions", "pos_line_items", "t2_doc_inventory",
    "log_files",
}
# doc source_types searched by doc_search / kb_search (narrative + reference layers)
_DOC_SOURCE_TYPES = ("doc_chat", "doc", "report_section", "render_ocr", "markdown_table")

# Auto value-hints: a column is treated as a categorical worth surfacing its real
# literals if it has at most _HINT_MAX distinct values. Columns whose NAME matches
# _HINT_SKIP (ids, dates, free text, names, numerics) are never hinted. This is a
# structural heuristic only -- no table-, column-, or answer-specific names -- so the
# model reads real values from whatever DB is attached instead of guessing or relying
# on hard-coded literals.
_HINT_MAX = 25
_HINT_MAXLEN = 2000
_HINT_BUDGET = 6000  # total chars of value hints to emit (keeps the prompt bounded)
_HINT_SKIP = re.compile(
    r"(^id$|_id$|_date$|date$|_at$|_seq$|timestamp|hash|path|filename|"
    r"email|phone|first_name|last_name|_name$|^name|title|text|content|"
    r"description|summary|bm25|embedding|metadata|warning|amount|_thb$|"
    r"quantity|units|value_numeric|numeric_value|percent)",
    re.IGNORECASE,
)


def _numeric_cast(col):
    """Return a DuckDB type to re-cast a VARCHAR numeric column to, or None."""
    c = col.lower()
    if c.endswith("_thb"):
        return "DECIMAL(18,2)"
    if c in ("quantity", "points_delta") or c.endswith("_units") or c.endswith("_qty"):
        return "BIGINT"
    if c in ("value_numeric", "numeric_value", "percent_value"):
        return "DECIMAL(18,4)"
    return None


def _cell(v):
    """Coerce a DuckDB cell into a JSON-serializable value."""
    if isinstance(v, Decimal):
        f = float(v)
        return int(f) if f.is_integer() else f
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v.isoformat()
    return v


class Tools:
    def __init__(self, db_path):
        self.con = duckdb.connect()  # in-memory, writable (default catalog)
        safe = db_path.replace("'", "''")
        self.con.execute(f"ATTACH '{safe}' AS src (READ_ONLY)")
        self._schema_cache = None
        self._build_views()

    def _build_views(self):
        rows = self.con.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_catalog='src' AND table_schema='main' "
            "ORDER BY table_name, ordinal_position"
        ).fetchall()
        by_table = {}
        for tbl, col in rows:
            by_table.setdefault(tbl, []).append(col)
        for tbl, cols in by_table.items():
            if not (tbl.startswith(_BUSINESS_PREFIXES) or tbl in _BUSINESS_EXTRA):
                continue
            repl = [f'TRY_CAST("{c}" AS {t}) AS "{c}"'
                    for c in cols if (t := _numeric_cast(c))]
            if repl:
                sql = (f'CREATE VIEW "{tbl}" AS '
                       f'SELECT * REPLACE ({", ".join(repl)}) FROM src."{tbl}"')
            else:
                sql = f'CREATE VIEW "{tbl}" AS SELECT * FROM src."{tbl}"'
            self.con.execute(sql)

    def _rows_as_dicts(self, sql, args=None):
        res = self.con.execute(sql, args or [])
        cols = [d[0] for d in res.description] if res.description else []
        return [{c: _cell(v) for c, v in zip(cols, row)} for row in res.fetchall()]

    def _columns_of(self, table):
        try:
            return [r[0] for r in self.con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_catalog='memory' AND lower(table_name)=lower(?) "
                "ORDER BY ordinal_position", [table]).fetchall()]
        except Exception:  # noqa: BLE001
            return []

    # -- universal read-only SQL ------------------------------------------------
    def run_sql(self, sql, limit=200):
        s = sql.strip().rstrip(";")
        low = s.lower()
        if not (low.startswith("select") or low.startswith("with")):
            return {"error": "only SELECT/WITH queries are allowed"}
        forbidden = (" insert ", " update ", " delete ", " drop ", " alter ",
                     " create ", " attach ", " pragma ", " copy ", " install ", " load ")
        if any(f in f" {low} " for f in forbidden):
            return {"error": "write/DDL statements are not allowed"}
        try:
            res = self.con.execute(s)
            rows = res.fetchmany(limit)
            cols = [d[0] for d in res.description] if res.description else []
            return {"columns": cols,
                    "rows": [[_cell(v) for v in r] for r in rows],
                    "row_count": len(rows)}
        except Exception as e:  # noqa: BLE001 - surface SQL error back to the model for self-repair
            msg = f"SQL error: {e}"
            # on a name error, surface the REAL columns of the referenced tables so the
            # model can correct the exact name instead of guessing or giving up.
            if re.search(r"not\s+found|no\s+such|binder|catalog|referenced column", str(e), re.I):
                referenced = re.findall(r"\b(?:from|join)\s+([A-Za-z_][\w]*)", s, re.I)
                actual = {t: self._columns_of(t) for t in dict.fromkeys(referenced) if self._columns_of(t)}
                if actual:
                    msg += " | actual columns available: " + json.dumps(actual, ensure_ascii=False)
            return {"error": msg}

    # -- deterministic "who currently holds this title" resolver ----------------
    def current_role_holder(self, title):
        title = (title or "").strip()
        if not title:
            return {"note": "provide a title, e.g. CEO"}
        try:
            rows = self._rows_as_dicts(
                "SELECT employee_id, first_name_en, last_name_en, position_title, "
                "canon_role_label, status FROM dim_employee WHERE position_title ILIKE ?",
                [f"%{title}%"])
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
        if not rows:
            return {"found": False, "note": f"no employee with position_title like '{title}'"}
        # exclude rows whose canon_role_label marks them as a predecessor; if exactly one
        # remains it is the current holder. No names/ids are hard-coded — this keys off the
        # generic predecessor markers in canon_role_label.
        pred = re.compile(r"founder|outgoing|former|predecessor|retired|emeritus|\bex[ -]", re.I)
        current = [r for r in rows if not pred.search(r.get("canon_role_label") or "")]
        if len(current) == 1:
            return {"found": True, "current": current[0], "all_rows": rows}
        return {"found": True, "current": None, "candidates": rows,
                "note": "multiple rows share this title; pick the successor by canon_role_label"}

    # -- general duplicate finder (no date scoping unless asked) ----------------
    def find_duplicates(self, table=None, column=None, scope_column=None, scope_value=None, limit=50):
        if not table or not column:
            return {"note": "provide table and column"}
        where, args = "", []
        if scope_column and scope_value is not None:
            where = f'WHERE "{scope_column}" = ?'
            args = [scope_value]
        sql = (f'SELECT "{column}" AS value, COUNT(*) AS n FROM "{table}" {where} '
               f'GROUP BY "{column}" HAVING COUNT(*) > 1 ORDER BY n DESC LIMIT {int(limit)}')
        try:
            rows = self._rows_as_dicts(sql, args)
            return {"table": table, "column": column, "duplicates": rows,
                    "duplicate_count": len(rows)}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    # -- incident / planted-marker lookup over the rag chunk layer --------------
    def claim_lookup(self, domain=None, claim_type=None, date_from=None, date_to=None, limit=20):
        # DOC_CLAIM no longer exists; planted incident markers (DQ3/DQ4/E9/L*/CEO ...)
        # live in the narrative chunks. Split a pipe/comma/space list so a model that
        # passes the whole enum verbatim still matches a real domain (OR across tokens).
        terms = []
        for raw in (domain, claim_type):
            if raw:
                terms += [t for t in re.split(r"[|,\s]+", raw) if t]
        if not terms:
            return {"rows": [], "note": "provide a domain or claim_type"}
        ors = " OR ".join(["content ILIKE ? OR bm25_text ILIKE ?"] * len(terms))
        args = []
        for t in terms:
            args += [f"%{t}%", f"%{t}%"]
        # the date is encoded in the source filename when present (no date column);
        # match a single day as a substring rather than an ordered comparison.
        date_clause = ""
        if date_from and date_from == date_to:
            date_clause = " AND (source_name ILIKE ? OR content ILIKE ?)"
            args += [f"%{date_from}%", f"%{date_from}%"]
        sql = ("SELECT chunk_id, source_type, source_name, title, "
               "substr(content,1,500) AS snippet FROM src.rag_chunks "
               f"WHERE ({ors}){date_clause} LIMIT {int(limit)}")
        try:
            return {"rows": self._rows_as_dicts(sql, args)}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    # -- bitemporal as-of-date policy resolver (SCD-2, never "latest") ----------
    def policy_resolver(self, policy_variable, as_of_date):
        sql = ("SELECT policy_variable, value_numeric, value_text, effective_date, end_date "
               "FROM dim_policy_version WHERE policy_variable = ? AND effective_date <= ? "
               "AND (end_date IS NULL OR end_date = '' OR ? <= end_date) "
               "ORDER BY effective_date DESC LIMIT 1")
        try:
            rows = self._rows_as_dicts(sql, [policy_variable, as_of_date, as_of_date])
            if not rows:
                return {"found": False, "note": f"no {policy_variable} policy in effect on {as_of_date}"}
            return {"found": True, "as_of_date": as_of_date, **rows[0]}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    # -- keyword/id retrieval over the rag chunk layer (chats/emails/memos/reports)
    def doc_search(self, query, channel=None, date_from=None, date_to=None, k=8):
        toks = [t for t in ID_TOKEN.findall(query) if len(t) > 1][:8]
        toks += THAI_TOKEN.findall(query)[:6]
        if not toks:
            return {"rows": [], "note": "no lexical tokens extracted"}
        ors = " OR ".join(["content ILIKE ? OR bm25_text ILIKE ?"] * len(toks))
        args = []
        for t in toks:
            args += [f"%{t}%", f"%{t}%"]
        types = ",".join("'%s'" % t for t in _DOC_SOURCE_TYPES)
        where = f"({ors}) AND source_type IN ({types})"
        if date_from and date_from == date_to:
            where += " AND (source_name ILIKE ? OR content ILIKE ?)"
            args += [f"%{date_from}%", f"%{date_from}%"]
        sql = ("SELECT chunk_id, source_type, source_name, title, "
               "substr(content,1,400) AS snippet FROM src.rag_chunks "
               f"WHERE {where} LIMIT {int(k)}")
        try:
            return {"rows": self._rows_as_dicts(sql, args)}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e), "tokens": toks}

    # -- search the L1 knowledge base / policy & product manuals ----------------
    def kb_search(self, query, k=3, max_chars=1500):
        toks = [t for t in ID_TOKEN.findall(query) if len(t) > 1]
        toks += THAI_TOKEN.findall(query)
        terms = toks[:8]
        if not terms:
            return {"rows": []}
        ors = " OR ".join(["content ILIKE ?"] * len(terms))
        args = [f"%{t}%" for t in terms]
        sql = ("SELECT source_name, title, content FROM src.rag_chunks "
               f"WHERE source_type='doc' AND ({ors}) LIMIT {int(k)}")
        try:
            rows = self._rows_as_dicts(sql, args)
            for r in rows:
                r["content"] = (r.get("content") or "")[:max_chars]
            return {"rows": rows}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    # -- search internal/customer chat threads by keyword + channel + date -------
    def chat_search(self, query=None, keywords=None, channel=None,
                    date=None, date_from=None, date_to=None, limit=30):
        where, args = ["1=1"], []
        if channel:
            ch = str(channel).lower()
            if "work" in ch:            # internal staff threads
                where.append("source_folder = 'chat_line_works'")
            elif "oa" in ch or "custom" in ch or "laai" in ch:  # customer-facing
                where.append("source_folder = 'chat_line_oa'")
            else:
                where.append("source_folder ILIKE ?"); args.append(f"%{channel}%")
        if date:
            where.append("chat_date = ?"); args.append(date)
        else:
            if date_from:
                where.append("chat_date >= ?"); args.append(date_from)
            if date_to:
                where.append("chat_date <= ?"); args.append(date_to)
        toks = []
        if keywords:
            toks = keywords if isinstance(keywords, list) else [keywords]
        elif query:
            toks = [t for t in ID_TOKEN.findall(query) if len(t) > 1][:6]
            toks += THAI_TOKEN.findall(query)[:6]
        if toks:
            where.append("(" + " OR ".join(["text ILIKE ?"] * len(toks)) + ")")
            args += [f"%{t}%" for t in toks]
        sql = ("SELECT chat_session_id, chat_date, source_folder, speaker, "
               "substr(text,1,400) AS text FROM docs_chat_messages "
               f"WHERE {' AND '.join(where)} ORDER BY chat_date, chat_session_id, message_seq "
               f"LIMIT {int(limit)}")
        try:
            rows = self._rows_as_dicts(sql, args)
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
        sessions = sorted({r.get("chat_session_id") for r in rows if r.get("chat_session_id")})
        return {"rows": rows, "message_count": len(rows),
                "thread_count": len(sessions), "thread_ids": sessions[:50]}

    # -- fetch a document/memo/report in full by id or keyword -------------------
    def get_doc(self, doc_id=None, query=None, max_chars=4000, limit=3):
        key = (doc_id or query or "").strip()
        if not key:
            return {"rows": [], "note": "provide doc_id or query"}
        like = f"%{key}%"
        sql = ("SELECT source_type, source_name, title, substr(content,1,?) AS content "
               "FROM src.rag_chunks "
               "WHERE source_name ILIKE ? OR title ILIKE ? "
               "ORDER BY length(content) DESC LIMIT ?")
        try:
            return {"rows": self._rows_as_dicts(sql, [int(max_chars), like, like, int(limit)])}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    # -- EDA discovery: real column values / a table's columns / find a field ---
    def inspect(self, kind=None, table=None, column=None, keyword=None, limit=40):
        kind = (kind or ("search" if keyword else "values" if column else "columns")).lower()
        if kind == "values" and table and column:
            try:
                vals = [_cell(r[0]) for r in self.con.execute(
                    f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL '
                    f"LIMIT {int(limit)}").fetchall()]
                return {"table": table, "column": column, "distinct_values": vals,
                        "truncated": len(vals) >= limit}
            except Exception as e:  # noqa: BLE001
                return {"error": str(e)}
        if kind == "columns" and table:
            cols = self._columns_of(table)
            if not cols:
                return {"error": f"no table '{table}' in schema"}
            try:
                sample = self._rows_as_dicts(f'SELECT * FROM "{table}" LIMIT 2')
            except Exception:  # noqa: BLE001
                sample = []
            return {"table": table, "columns": cols, "sample_rows": sample}
        if kind == "search" and keyword:
            like = f"%{keyword}%"
            try:
                hits = self._rows_as_dicts(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_catalog='memory' AND (table_name ILIKE ? OR column_name ILIKE ?) "
                    "ORDER BY table_name, ordinal_position LIMIT 60", [like, like])
            except Exception as e:  # noqa: BLE001
                return {"error": str(e)}
            return {"keyword": keyword, "matches": hits, "found": len(hits) > 0}
        return {"note": "use kind=values (table+column) | columns (table) | search (keyword)"}

    # -- compact schema card with auto-derived value hints (schema-linking aid) -
    def schema_card(self):
        if self._schema_cache is not None:
            return self._schema_cache
        tables = [r[0] for r in self.con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_catalog='memory' AND table_schema='main' ORDER BY table_name").fetchall()]
        cols_by_table, lines = {}, []
        for t in tables:
            cols = [r[0] for r in self.con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_catalog='memory' AND table_name=? ORDER BY ordinal_position",
                [t]).fetchall()]
            cols_by_table[t] = cols
            lines.append(f"{t}({', '.join(cols)})")
        # auto-derive real literals for low-cardinality categorical columns so the model
        # filters on actual values instead of guessing. dim_/fact_ tables first, then the
        # rest, under a total size budget so the prompt stays bounded.
        hints, budget = {}, _HINT_BUDGET
        ordered = sorted(tables, key=lambda t: (0 if t.startswith(_BUSINESS_PREFIXES) else 1, t))
        for t in ordered:
            if budget <= 0:
                break
            for col in cols_by_table[t]:
                if not col.isascii() or _HINT_SKIP.search(col):
                    continue
                try:
                    vals = [str(r[0]) for r in self.con.execute(
                        f'SELECT DISTINCT "{col}" FROM "{t}" '
                        f'WHERE "{col}" IS NOT NULL AND CAST("{col}" AS VARCHAR) <> \'\' '
                        f"LIMIT {_HINT_MAX + 1}").fetchall()]
                except Exception:  # noqa: BLE001
                    continue
                size = sum(len(v) for v in vals)
                if 1 <= len(vals) <= _HINT_MAX and size <= _HINT_MAXLEN and size <= budget:
                    hints[f"{t}.{col}"] = vals
                    budget -= size
        self._schema_cache = ("\n".join(lines), hints)
        return self._schema_cache

    def close(self):
        self.con.close()


if __name__ == "__main__":
    import sys
    t = Tools(sys.argv[1] if len(sys.argv) > 1 else "fahmai.duckdb")
    card, hints = t.schema_card()
    print("TABLES:\n", card[:800], "...\n")
    print("HINTS:", json.dumps(hints, ensure_ascii=False)[:500])
    print("\nvendor top3:", json.dumps(
        t.run_sql("SELECT vendor_id, SUM(paid_amount_thb) t FROM fact_vendor_payment GROUP BY 1 ORDER BY 2 DESC LIMIT 3"),
        ensure_ascii=False))
    print("claim DQ4:", json.dumps(t.claim_lookup("DQ4"), ensure_ascii=False)[:300])
