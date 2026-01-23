from sqlalchemy import Column, Integer, String  
from app.core.database import get_db_connection
import psycopg2
from psycopg2.extras import RealDictCursor

def getParcelas4HistMeteo(id_parcela=None):
    conn = get_db_connection()
    try:

        query = """
            SELECT uid_parcel, coordinates_parcel
            FROM parcels
        """
        params = []
        
        if id_parcela is not None:
            query += " WHERE uid_parcel = %s"
            params.append(id_parcela)

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            parcelas = cur.fetchall()  # ← Recupera TODAS las filas
            return parcelas  # lista de dicts

    except Exception as e:
        conn.rollback()
        print(f"Error en getParcelas4HistMeteo: {e}")
        return []
    finally:
        conn.close()