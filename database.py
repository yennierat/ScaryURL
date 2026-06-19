import secrets, string, random
import psycopg2
from dotenv import load_dotenv
import os
import logging
from psycopg2.extensions import connection
from psycopg2 import pool


load_dotenv() # load the local variables

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

connection_pool = pool.ThreadedConnectionPool(1, 10, os.environ["DATABASE_URL"])

PREFIXES = ["lottery", "claim", "verify", "account", "secure", "free-gift","loan","login","moneyz","banking","account-update","secure-login","install","update","redeem"]
SUFFIXES = ["now", "today", "urgent", "limited"]

def get_db() -> connection:
    return connection_pool.getconn()

def return_db(conn: connection) -> None:
    connection_pool.putconn(conn)

def init_db() -> None:
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS urls(
                    id SERIAL PRIMARY KEY,
                    original_url TEXT NOT NULL,
                    combination TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    click_count INTEGER DEFAULT 0)
            """)
        db.commit()
    finally:
        return_db(db)

def generate_slug(combination: str) -> str:
    prefix = random.choice(PREFIXES)
    suffix = random.choice(SUFFIXES)
    return f"{prefix}_{combination}_{suffix}"

def generate_combination() -> str:
    chars = string.ascii_letters + string.digits # would generate 56.8 billion combinations (62 ** 6)
    combination = ''.join(secrets.choice(chars) for _ in range(6))
    return combination

def create_link(original_url: str) -> str | None:
    db = get_db()
    try:
        while True:
            combination = generate_combination()
            try:
                with db.cursor() as cur:
                    cur.execute(
                        "INSERT INTO urls (original_url, combination) VALUES (%s, %s)",
                        (original_url, combination)
                    )
                db.commit()
                return combination
            except psycopg2.errors.UniqueViolation:
                db.rollback() # need to revert changes before retrying a collision.
                logger.warning(f"Combination collision: {combination}, retrying...")
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                raise
    finally:
        return_db(db)

def get_existing_combination(original_url: str) -> str | None:
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT combination FROM urls WHERE original_url = %s",
                (original_url,)
            )
            row = cur.fetchone()
        db.commit() # need to commit to save changes
        return row[0] if row else None
    finally:
        return_db(db)

def get_link(combination: str) -> str | None:
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT original_url FROM urls WHERE combination = %s", (combination,)
            )
            url = cur.fetchone()
        db.commit()
        return url[0] if url else None
    finally:
        return_db(db)

def increment_clicks(combination: str) -> None:
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "UPDATE urls SET click_count = click_count + 1 WHERE combination = %s", (combination,)
            )
        db.commit()
    finally:
        return_db(db)
