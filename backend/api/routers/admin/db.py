from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text as sql_text
from sqlmodel import Session

from api.core.database import get_session
from api.models.podcast import Episode, Podcast, PodcastTemplate
from api.models.user import User

from .deps import get_current_admin_user

router = APIRouter()

DB_EXPLORER_TABLES = ["user", "podcast", "episode", "podcasttemplate", "podcast_template"]
DB_MODEL_MAP = {
    "user": User,
    "podcast": Podcast,
    "episode": Episode,
    "podcasttemplate": PodcastTemplate,
    "podcast_template": PodcastTemplate,
}


def _exec_text(session: Session, sql: str, params: Optional[dict] = None):
    statement = sql_text(sql)
    if params:
        return session.execute(statement, params)
    return session.execute(statement)


def _quote_ident(name: str) -> str:
    if name is None:
        return '""'
    return '"' + str(name).replace('"', '""') + '"'


def _find_table_schema_and_columns(session: Session, table_name: str) -> tuple[Optional[str], List[str]]:
    """Find table schema and columns (PostgreSQL only)."""
    bind = session.get_bind()
    
    try:
        inspector = sa_inspect(bind)
    except Exception:
        return None, []

    probe_schemas: List[Optional[str]] = [None, "public"]
    try:
        for schema in inspector.get_schema_names():
            if schema not in probe_schemas:
                probe_schemas.append(schema)
    except Exception:
        pass

    for schema in probe_schemas:
        try:
            has_tbl = False
            try:
                has_tbl = inspector.has_table(table_name, schema=schema)  # type: ignore[arg-type]
            except Exception:
                pass
            if has_tbl or True:
                try:
                    cols_meta = inspector.get_columns(table_name, schema=schema)
                    if cols_meta:
                        return schema, [col["name"] for col in cols_meta]
                except Exception:
                    continue
        except Exception:
            continue
    return None, []


def _db_rows_to_dicts(result) -> List[Dict[str, Any]]:
    try:
        return [dict(row) for row in result.mappings().all()]
    except Exception:
        rows = result.fetchall()
        keys = result.keys() if hasattr(result, "keys") else []
        return [dict(zip(keys, row)) for row in rows]


@router.get("/db/tables", status_code=200)
def admin_db_tables(
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    del admin_user
    existing: List[str] = []
    for table in DB_EXPLORER_TABLES:
        _, cols = _find_table_schema_and_columns(session, table)
        if cols:
            existing.append(table)
    return {"tables": existing}


@router.get("/db/table/{table_name}", status_code=200)
def admin_db_table_rows(
    table_name: str,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    del admin_user
    if table_name not in DB_EXPLORER_TABLES:
        raise HTTPException(status_code=400, detail="Table not allowed")
    if limit <= 0:
        limit = 50
    if limit > 500:
        limit = 500
    if offset < 0:
        offset = 0
    try:
        schema, columns = _find_table_schema_and_columns(session, table_name)
        if not columns:
            return {"table": table_name, "columns": [], "rows": [], "total": 0, "offset": offset, "limit": limit}
        if table_name == "episode" and "publish_at" in columns:
            order_clause = f"{_quote_ident('publish_at')} DESC"
        else:
            preferred = ["created_at", "processed_at", "publish_at", "published_at", "id"]
            chosen = next((col for col in preferred if col in columns), columns[0])
            order_clause = f"{_quote_ident(chosen)} DESC"
        tbl_sql = f"{_quote_ident(schema)}.{_quote_ident(table_name)}" if schema else _quote_ident(table_name)
        total_res = _exec_text(session, f"SELECT COUNT(*) FROM {tbl_sql}")
        total = total_res.first()[0]
        rows_res = _exec_text(
            session,
            f"SELECT * FROM {tbl_sql} ORDER BY {order_clause} LIMIT :lim OFFSET :off",
            {"lim": limit, "off": offset},
        )
        rows = _db_rows_to_dicts(rows_res)
        return {"table": table_name, "columns": columns, "rows": rows, "total": total, "offset": offset, "limit": limit}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}")


@router.get("/db/table/{table_name}/{row_id}", status_code=200)
def admin_db_table_row_detail(
    table_name: str,
    row_id: str,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    del admin_user
    if table_name not in DB_EXPLORER_TABLES:
        raise HTTPException(status_code=400, detail="Table not allowed")
    pk_col = "id"
    try:
        schema, _ = _find_table_schema_and_columns(session, table_name)
        tbl_sql = f"{_quote_ident(schema)}.{_quote_ident(table_name)}" if schema else _quote_ident(table_name)
        res = _exec_text(session, f"SELECT * FROM {tbl_sql} WHERE {_quote_ident(pk_col)} = :rid", {"rid": row_id})
        row_map = res.mappings().first()
        if not row_map:
            raise HTTPException(status_code=404, detail="Row not found")
        return {"table": table_name, "row": dict(row_map)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lookup failed: {exc}")


class RowUpdatePayload(BaseModel):
    updates: dict


@router.patch("/db/table/{table_name}/{row_id}", status_code=200)
def admin_db_table_row_update(
    table_name: str,
    row_id: str,
    payload: RowUpdatePayload,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    del admin_user
    if table_name not in DB_EXPLORER_TABLES:
        raise HTTPException(status_code=400, detail="Table not allowed")
    updates = payload.updates or {}
    if not isinstance(updates, dict) or not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    schema, column_names = _find_table_schema_and_columns(session, table_name)
    protected = {"id", "created_at", "processed_at", "publish_at", "published_at", "spreaker_episode_id"}
    set_parts = []
    params = {"rid": row_id}
    for key, value in updates.items():
        if key not in column_names:
            continue
        if key in protected:
            continue
        param_name = f"val_{key}"
        set_parts.append(f"{_quote_ident(key)} = :{param_name}")
        params[param_name] = value
    if not set_parts:
        raise HTTPException(status_code=400, detail="No permissible fields to update")
    tbl_sql = f"{_quote_ident(schema)}.{_quote_ident(table_name)}" if schema else _quote_ident(table_name)
    sql = f"UPDATE {tbl_sql} SET {', '.join(set_parts)} WHERE {_quote_ident('id')} = :rid"
    try:
        _exec_text(session, sql, params)
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Update failed: {exc}")
    return admin_db_table_row_detail(table_name, row_id, session, admin_user)


class RowInsertPayload(BaseModel):
    values: dict


@router.post("/db/table/{table_name}", status_code=201)
def admin_db_table_row_insert(
    table_name: str,
    payload: RowInsertPayload,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    del admin_user
    if table_name not in DB_EXPLORER_TABLES:
        raise HTTPException(status_code=400, detail="Table not allowed")
    values = payload.values or {}
    if not isinstance(values, dict) or not values:
        raise HTTPException(status_code=400, detail="No values provided")
    schema, column_names = _find_table_schema_and_columns(session, table_name)
    if not column_names:
        raise HTTPException(status_code=400, detail="Unknown table or no columns")
    protected = {"created_at", "processed_at", "publish_at", "published_at", "spreaker_episode_id"}
    params: Dict[str, Any] = {}
    insert_cols: List[str] = []
    for key, value in values.items():
        if key not in column_names or key in protected:
            continue
        insert_cols.append(key)
        params[f"val_{key}"] = value
    if "id" in column_names and "id" not in values:
        new_id = str(uuid4())
        insert_cols.append("id")
        params["val_id"] = new_id
    row_id = values.get("id") or params.get("val_id")
    if not insert_cols:
        raise HTTPException(status_code=400, detail="No permissible fields to insert")
    placeholders = ", ".join([f":val_{col}" for col in insert_cols])
    cols_sql = ", ".join(_quote_ident(col) for col in insert_cols)
    tbl_sql = f"{_quote_ident(schema)}.{_quote_ident(table_name)}" if schema else _quote_ident(table_name)
    sql = f"INSERT INTO {tbl_sql} ({cols_sql}) VALUES ({placeholders})"
    try:
        _exec_text(session, sql, params)
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Insert failed: {exc}")
    if row_id is not None:
        return admin_db_table_row_detail(table_name, str(row_id), session, admin_user)
    return {"table": table_name, "inserted": True, "values": {key: values.get(key) for key in insert_cols}}


@router.delete("/db/table/{table_name}/{row_id}", status_code=200)
def admin_db_table_row_delete(
    table_name: str,
    row_id: str,
    session: Session = Depends(get_session),
    admin_user: User = Depends(get_current_admin_user),
):
    del admin_user
    if table_name not in DB_EXPLORER_TABLES:
        raise HTTPException(status_code=400, detail="Table not allowed")
    model = DB_MODEL_MAP.get(table_name)
    if model is not None:
        try:
            identifier: Any = row_id
            try:
                identifier = UUID(str(row_id))
            except Exception:
                identifier = row_id
            obj = session.get(model, identifier)
            if not obj:
                raise HTTPException(status_code=404, detail="Row not found")
            session.delete(obj)
            session.commit()
        except HTTPException:
            raise
        except Exception as exc:
            session.rollback()
            raise HTTPException(status_code=500, detail=f"Delete failed: {exc}")
    else:
        try:
            schema, _ = _find_table_schema_and_columns(session, table_name)
            tbl_sql = f"{_quote_ident(schema)}.{_quote_ident(table_name)}" if schema else _quote_ident(table_name)
            _exec_text(session, f"DELETE FROM {tbl_sql} WHERE {_quote_ident('id')} = :rid", {"rid": row_id})
            session.commit()
        except Exception as exc:
            session.rollback()
            raise HTTPException(status_code=500, detail=f"Delete failed: {exc}")
    return {"deleted": True, "table": table_name, "id": row_id}


__all__ = ["router"]
