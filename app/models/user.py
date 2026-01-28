from sqlalchemy import Column, Integer, String  # ← Quita Base
# from app.core.database import Base  # ← ELIMINA ESTA LÍNEA
from app.core.database import get_db_connection
import psycopg2
from psycopg2.extras import RealDictCursor
import hashlib  # ✅ Para hashear contraseña

# ✅ Mantén SOLO las funciones:
def verify_user_credentials(email: str, password: str):
    conn = get_db_connection()
    try:
        # ✅ HASHEAR la contraseña que viene del login ANTES de comparar
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, email, nombre, password_hash 
                FROM usuarios 
                WHERE email = %s AND password_hash = %s
            """, (email, password_hash))  # ✅ Ahora sí coincide
            return cur.fetchone()
    finally:
        conn.close()