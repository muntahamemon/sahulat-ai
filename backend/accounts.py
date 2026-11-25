import hashlib
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager

from fastapi import HTTPException, Request, Response

COOKIE = "sahulat_session"
SESSION_SECONDS = 7 * 24 * 60 * 60

@contextmanager
def database():
    url = os.getenv("DATABASE_URL")
    if url:
        import psycopg
        connection = psycopg.connect(url)
    elif os.getenv("VERCEL"):
        raise HTTPException(503, "Account storage is not configured.")
    else:
        connection = sqlite3.connect(os.getenv("SAHULAT_DB_PATH", "data/sahulat.sqlite3"))
    try:
        with connection:
            def execute(sql, values=()):
                return connection.execute(sql.replace("?", "%s") if url else sql, values)

            execute("CREATE TABLE IF NOT EXISTS accounts (email TEXT PRIMARY KEY, name TEXT NOT NULL, password TEXT NOT NULL)")
            execute("CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, email TEXT NOT NULL, expires BIGINT NOT NULL)")
            execute("CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, email TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL, created TEXT NOT NULL)")
            yield execute
    finally:
        connection.close()

def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()

def session_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()

def start_session(execute, request: Request, response: Response, email):
    token = secrets.token_urlsafe(32)
    end = int(time.time()) + SESSION_SECONDS
    old = request.cookies.get(COOKIE)
    if old:
        execute("DELETE FROM sessions WHERE token = ?", (session_digest(old),))
    execute("DELETE FROM sessions WHERE expires <= ?", (int(time.time()),))
    execute("INSERT INTO sessions VALUES (?, ?, ?)", (session_digest(token), email, end))
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=bool(os.getenv("VERCEL")) or request.url.scheme == "https", samesite="lax")

def account_for(execute, request: Request):
    token = request.cookies.get(COOKIE)
    if token:
        account = execute(
            "SELECT a.email, a.name FROM accounts a JOIN sessions s ON a.email = s.email WHERE s.token = ? AND s.expires > ?",
            (session_digest(token), int(time.time())),
        ).fetchone()
        if account:
            return {"email": account[0], "name": account[1]}
    raise HTTPException(401, "Log in to continue.")
