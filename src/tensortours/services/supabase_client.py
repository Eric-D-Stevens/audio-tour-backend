"""Supabase (Postgres) connection client for TensorTours POI system."""

import logging
import os
from functools import lru_cache
from typing import Optional

import psycopg2
import psycopg2.extensions

from ..utils.aws import get_secret, parse_json_secret

logger = logging.getLogger(__name__)

SUPABASE_DB_SECRET_NAME = os.environ.get("SUPABASE_DB_SECRET_NAME", "")


@lru_cache(maxsize=1)
def _get_db_url() -> str:
    """Fetch the Supabase DB URL from Secrets Manager.

    Cached so Secrets Manager is only called once per warm Lambda instance.
    """
    secret = get_secret(SUPABASE_DB_SECRET_NAME)
    url = parse_json_secret(secret).get("SUPABASE_DB_URL", "")
    if not url:
        raise ValueError(
            f"SUPABASE_DB_URL not found in secret '{SUPABASE_DB_SECRET_NAME}'"
        )
    return url


def get_connection(
    user_id: Optional[str] = None,
) -> psycopg2.extensions.connection:
    """Open a new psycopg2 connection to Supabase.

    Connections are NOT cached — Lambda instances are short-lived and
    pgbouncer (port 6543) handles connection pooling on the Supabase side.

    Args:
        user_id: Optional Cognito sub to set as app.current_user_id for RLS.
    """
    conn = psycopg2.connect(_get_db_url())
    if user_id:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT set_config('app.current_user_id', %s, false)", [user_id]
            )
    return conn
