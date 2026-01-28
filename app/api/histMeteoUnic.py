import schedule
import time
import requests
import pandas as pd
import logging
import ast

from sqlalchemy import Column, Integer, String 
from psycopg2.extras import RealDictCursor

import psycopg2
import os
from dotenv import load_dotenv


import time
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import execute_values


# Configura logging para ver las ejecuciones
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

def get_db_connection():
    """Conexión escalable a PostgreSQL"""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', ''),
        port=os.getenv('DB_PORT', ''),
        database=os.getenv('DB_NAME', ''),
        user=os.getenv('DB_USER', ''),
        password=os.getenv('DB_PASSWORD', '')
    )

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

def save_meteo_histo(df: pd.DataFrame):
    conn = get_db_connection()
    try:
        """
        Inserta datos en weather_archive evitando duplicados exactos
        (mismo uid_parcel, time, temp_max, temp_min, rain, humidity_mean, humidity_min, humidity_max).
        """
        sql = """
        INSERT INTO weather_archive
        (uid_parcel, time, temp_max, temp_min, rain, humidity_mean, humidity_min, humidity_max)
        SELECT %s, %s, %s, %s, %s, %s, %s, %s
        WHERE NOT EXISTS (
            SELECT 1 FROM weather_archive
            WHERE uid_parcel = %s
            AND time = %s
            AND temp_max = %s
            AND temp_min = %s
            AND rain = %s
            AND humidity_mean = %s
            AND humidity_min = %s
            AND humidity_max = %s
        )
        """
        
        with conn.cursor() as cur:
            for _, row in df.iterrows():
                values = (
                    row['field'], row['time'].date(), row['temp_max'], row['temp_min'],
                    row['rain'], row['humidity_mean'], row['humidity_min'], row['humidity_max'],
                    # Para el WHERE NOT EXISTS
                    row['field'], row['time'].date(), row['temp_max'], row['temp_min'],
                    row['rain'], row['humidity_mean'], row['humidity_min'], row['humidity_max']
                )
                cur.execute(sql, values)
            conn.commit()
        print(f"{len(df)} registros procesados (duplicados exactos evitados).")


    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()



def fetch_meteo_data_histo(id_parcela):
    """Función que hace la llamada a Open-Meteo cada 15 min"""
    parcelas = getParcelas4HistMeteo(id_parcela)

    # Fecha de hoy
    hoy = datetime.utcnow()

    # Fecha de hace 4 días
    hace_4_dias = hoy - timedelta(days=4)

    # Convertir a string en formato YYYY-MM-DD
    fecha_inicio = hace_4_dias.strftime('%Y-%m-%d')
    fecha_fin = hoy.strftime('%Y-%m-%d')
    all_dfs = []


    for row in parcelas:
        uid = row["uid_parcel"]
        coords = row["coordinates_parcel"]
        coords_list = ast.literal_eval(coords)
        lat=coords_list[0][0]
        long=coords_list[0][1]
        try:
            url = "https://archive-api.open-meteo.com/v1/archive"

            params = {
                "latitude": lat,
                "longitude": long,
                "start_date": fecha_inicio,
                "end_date": fecha_fin,
                "hourly": "relative_humidity_2m",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
                "timezone": "auto"
            }

            r = requests.get(url, params=params)
            r.raise_for_status()
            data = r.json()
            # ---- HUMEDAD HORARIA → DIARIA ----
            df_h = pd.DataFrame(data["hourly"])
            df_h["time"] = pd.to_datetime(df_h["time"])
            df_h = (
                df_h.groupby(df_h["time"].dt.date)["relative_humidity_2m"]
                .agg(["mean", "min", "max"])
                .round(1)
                .reset_index()
            )
            df_h.columns = ["time", "humidity_mean", "humidity_min", "humidity_max"]
            df_h["time"] = pd.to_datetime(df_h["time"])
            # ---- DAILY ----
            df_d = pd.DataFrame(data["daily"])
            df_d.columns = ["time", "temp_max", "temp_min",   "rain"]
            df_d["time"] = pd.to_datetime(df_d["time"])
            df = pd.merge(df_d, df_h, on="time", how="inner")
            df["field"] = uid
            all_dfs.append(df)
               
            # Aquí guardas los datos (base de datos, CSV, etc.)
            #print(f"Datos obtenidos: \n\r{all_dfs}")
            
            save_meteo_histo(df)
            
        except Exception as e:
            logger.error(f"Error en consulta meteo: {e}")


