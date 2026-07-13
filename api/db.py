import psycopg
from pgvector.psycopg import register_vector

from api.config import settings


def get_connection():
    """
    Opens a fresh connection with the pgvector type adapter registered,
    so Python lists convert to/from Postgres 'vector' columns automatically.
    Used as a FastAPI dependency (see api/main.py) so each request gets
    its own connection and nothing leaks across requests.
    """
    conn = psycopg.connect(settings.database_url, autocommit=True)
    register_vector(conn)
    return conn
