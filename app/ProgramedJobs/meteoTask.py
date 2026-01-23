import schedule
import time
import requests
import pandas as pd
import logging
import ast

from sqlalchemy import Column, Integer, String  # ← Quita Base
# from app.core.database import Base  # ← ELIMINA ESTA LÍNEA
import psycopg2
from psycopg2.extras import RealDictCursor

import psycopg2
import os
from dotenv import load_dotenv



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

def getParcelas4HistMeteo():
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT uid_parcel, coordinates_parcel
                FROM parcels
            """)
            parcelas = cur.fetchall()  # ← Recupera TODAS las filas
            return parcelas  # lista de dicts

    except Exception as e:
        conn.rollback()
        print(f"Error en getParcelas4HistMeteo: {e}")
        return []
    finally:
        conn.close()

def save_meteo_forecast(uid_parcel: str, df: pd.DataFrame):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for _, row in df.iterrows():
                cur.execute(
                    """
                    INSERT INTO meteo_forecast (
                        uid_parcel,
                        time,
                        temperature,
                        relative_humidity,
                        precipitation,
                        cloud_cover,
                        wind_speed,
                        wind_direction
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        uid_parcel,
                        row["time"],
                        row["temperature"],
                        row["relative_humidity"],
                        row["precipitation"],
                        row["cloud_cover"],
                        row["wind_speed"],
                        row["wind_direction"]
                    )
                )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()



def fetch_meteo_data():
    """Función que hace la llamada a Open-Meteo cada 15 min"""    
    print("**************************EEEEEEEEEENTROOOOO*************************")
    parcelas = getParcelas4HistMeteo()

    for row in parcelas:
        uid = row["uid_parcel"]
        coords = row["coordinates_parcel"]
        coords_list = ast.literal_eval(coords)
        lat=coords_list[0][0]
        long=coords_list[0][1]

        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": long,
            "current": "temperature_2m,relative_humidity_2m,precipitation,cloud_cover,wind_speed_10m,wind_direction_10m",
            "timezone": "auto"
        }
        
        try:
            r = requests.get(url, params=params)
            r.raise_for_status()
            data = r.json()
            cur = data["current"]
            
            df = pd.DataFrame([{
                "time": pd.to_datetime(cur["time"]),
                "temperature": cur["temperature_2m"],
                "relative_humidity": cur["relative_humidity_2m"],
                "precipitation": cur["precipitation"],
                "cloud_cover": cur["cloud_cover"],
                "wind_speed": cur["wind_speed_10m"],
                "wind_direction": cur["wind_direction_10m"]
            }])
            
            # Aquí guardas los datos (base de datos, CSV, etc.)
            # print(f"Datos obtenidos: {df.to_dict('records')}")
        
            save_meteo_forecast(uid, df)
            
        except Exception as e:
            logger.error(f"Error en consulta meteo: {e}")


fetch_meteo_data()

# Programa la tarea cada 15 minutos
schedule.every(60).minutes.do(fetch_meteo_data)


while True:
    schedule.run_pending()
    time.sleep(1)



