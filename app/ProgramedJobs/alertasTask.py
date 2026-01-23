# app/ProgramedJobs/alertasTask.py
import sys
import os
import time
from datetime import datetime

# Añadir raíz del proyecto al PATH
PROYECTO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROYECTO_ROOT)

# Core
import logging
import pandas as pd
import schedule

# SQLAlchemy y PostgreSQL
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert
import psycopg2
from psycopg2.extras import RealDictCursor

# HTTP y parsing
import requests
import ast


from dotenv import load_dotenv

# Configura logging para ver las ejecuciones
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

# INITIALIZAR ENGINE ← ¡ESTO FALTABA!
DATABASE_URL = os.getenv('DATABASE_URL', '')
if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL no está definida")

engine = create_engine(DATABASE_URL)


logger.info("🚀 AlertasTask iniciado con conexión BBDD")




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


def calcular_alertas():
    """Calcula alertas nocturnas y guarda en BBDD"""
    logger.info("=== ALERTAS NOCTURNAS 03:00 AM ===")
    
    now = datetime.now()
    logger.info(f"Procesando datos hasta {now.strftime('%Y-%m-%d %H:%M')}")

    all_data = []

    parcelas = getParcelas4HistMeteo()

    for row in parcelas:
        uid_parcel = row["uid_parcel"]
        coords = row["coordinates_parcel"]
        coords_list = ast.literal_eval(coords)
        lat=coords_list[0][0]
        long=coords_list[0][1]        
        
        url = "https://api.open-meteo.com/v1/forecast"

        params = {
            "latitude": lat,
            "longitude": long,
            "daily": (
                "temperature_2m_max,temperature_2m_min,"
                "precipitation_sum,relative_humidity_2m_max,"
                "relative_humidity_2m_min"
            ),
            "timezone": "auto"
        }
        
        r = requests.get(url, params=params)
        r.raise_for_status()
        data = r.json()

        daily = data["daily"]

        df = pd.DataFrame({
            "uid_parcel": uid_parcel,
            "date": pd.to_datetime(daily["time"]),
            "temp_max": daily["temperature_2m_max"],
            "temp_min": daily["temperature_2m_min"],
            "rain": daily["precipitation_sum"],
            "humidity_max": daily["relative_humidity_2m_max"],
            "humidity_min": daily["relative_humidity_2m_min"]
        })

        all_data.append(df)

    df_all = pd.concat(all_data, ignore_index=True)

    # ---------- FEATURES ----------

    df_all["temp_mean"] = (df_all["temp_max"] + df_all["temp_min"]) / 2
    df_all["temp_diff"] = df_all["temp_max"] - df_all["temp_min"]
    df_all["humidity_mean"] = (df_all["humidity_max"] + df_all["humidity_min"]) / 2

    df_all = df_all.sort_values(["uid_parcel", "date"])

    df_all["rain_3d_sum"] = (
        df_all.groupby("uid_parcel")["rain"]
        .rolling(3, min_periods=1)
        .sum()
        .reset_index(level=0, drop=True)
    )

    df_all["rain_7d_sum"] = (
        df_all.groupby("uid_parcel")["rain"]
        .rolling(7, min_periods=1)
        .sum()
        .reset_index(level=0, drop=True)
    )

    df_all["humidity_3d_mean"] = (
        df_all.groupby("uid_parcel")["humidity_mean"]
        .rolling(3, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )

    df_all["temp_7d_mean"] = (
        df_all.groupby("uid_parcel")["temp_mean"]
        .rolling(7, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    # print(df_all)    
    dfDatosConAlertas = add_alerts(df_all)
    # print(dfDatosConAlertas.columns)
    # print("dfDatosConAlertas: ")
    # print(dfDatosConAlertas)
    
    logger.info("Alertas nocturnas procesadas y guardadas")
    logger.info("=== FIN ALERTAS NOCTURNAS ===")
    
    return dfDatosConAlertas


# FUNCIÓN ALERTA HELADA

def riesgo_helada(row):
    score = 0

    # Temperatura mínima crítica
    if row["temp_min"] <= 0:
        score += 2   # helada directa

    elif row["temp_min"] <= 2:
        score += 1   # riesgo leve

    # Tendencia fría
    if row["temp_7d_mean"] <= 5:
        score += 1

    if score >= 3:
        return "ALTO"
    elif score == 2:
        return "MEDIO"
    else:
        return None

# FUNCIÓN ALERTA INUNDACIÓN

def riesgo_inundacion(row):
    score = 0

    if row["rain_3d_sum"] >= 40:
        score += 2
    elif row["rain_3d_sum"] >= 20:
        score += 1

    if row["rain_7d_sum"] >= 80:
        score += 1

    if row["humidity_mean"] >= 85:
        score += 1

    if score >= 3:
        return "ALTO"
    elif score == 2:
        return "MEDIO"
    else:
        return None

# FUNCIÓN ALERTA PLAGA

def riesgo_plaga(row):
    score = 0

    if row["humidity_3d_mean"] >= 80:
        score += 1
    if 15 <= row["temp_7d_mean"] <= 28:
        score += 1
    if row["rain_3d_sum"] >= 5:
        score += 1

    if score == 3:
        return "ALTO"
    elif score == 2:
        return "MEDIO"
    else:
        return None


def procesar_y_guardar_alertas(dfDatosConAlertas):
    """1. Lee histórico → 2. UPSERT datos actuales → 3. Log cambios"""
    
    logger.info("🔄 Iniciando procesamiento de alertas...")
    
    # 1. CARGAR HISTÓRICO desde BBDD
    historic_query = """
    SELECT uid_parcel, fecha, alerta_helada, alerta_inundacion, alerta_plaga
    FROM alertas 
    WHERE fecha >= CURRENT_DATE - INTERVAL '7 days'
    """
    
    historicAlertaDataFrame = pd.read_sql(historic_query, engine)
    logger.info(f"📥 Histórico cargado: {len(historicAlertaDataFrame)} registros")
    
    # 2. PREPARAR DataFrame actual para BBDD
    df_alertas = dfDatosConAlertas[[
        'uid_parcel', 'date', 'alerta_helada', 
        'alerta_inundacion', 'alerta_plaga'
    ]].copy()
    
    df_alertas.columns = ['uid_parcel', 'fecha', 'alerta_helada', 'alerta_inundacion', 'alerta_plaga']
    df_alertas['fecha'] = pd.to_datetime(df_alertas['fecha']).dt.date
    
    logger.info(f"📤 Datos actuales: {len(df_alertas)} registros")
    
    # 3. MÉTODO 1: UPSERT MÁGICO con función personalizada
    upsert_alertas(df_alertas)
    
    # 4. LOG CAMBIOS (opcional)
    cambios = comparar_cambios(historicAlertaDataFrame, df_alertas)
    logger.info(f"📊 Cambios detectados: {cambios}")
    
    logger.info("✅ Alertas procesadas correctamente")

def upsert_alertas(df):
    """Método mágico UPSERT para PostgreSQL"""
    
    
    df.to_sql(
        name='alertas',
        con=engine,
        if_exists='append',
        index=False,
        method=postgresql_upsert,
        chunksize=1000
    )

def postgresql_upsert(table, conn, keys, data_iter):
    """Función mágica para UPSERT (INSERT o UPDATE)"""
    
    data = [dict(zip(keys, row)) for row in data_iter]
    insert_stmt = insert(table.table).values(data)
    
    # UPSERT: Si existe → UPDATE, si no → INSERT
    upsert_stmt = insert_stmt.on_conflict_do_update(
        constraint='pk_alertas',  # Nombre de tu PK compuesta
        set_={
            'alerta_helada': insert_stmt.excluded.alerta_helada,
            'alerta_inundacion': insert_stmt.excluded.alerta_inundacion,
            'alerta_plaga': insert_stmt.excluded.alerta_plaga
        }
    )
    conn.execute(upsert_stmt)

def comparar_cambios(df_historico, df_actual):
    """Compara histórico vs actual para loggear cambios"""
    if df_historico.empty:
        return f"{len(df_actual)} nuevas alertas"
    
    # Merge para detectar cambios
    merged = df_actual.merge(
        df_historico, 
        on=['uid_parcel', 'fecha'], 
        how='left', 
        suffixes=('_actual', '_historico')
    )
    
    cambios = merged[
        (merged['alerta_helada_actual'] != merged['alerta_helada_historico']) |
        (merged['alerta_inundacion_actual'] != merged['alerta_inundacion_historico']) |
        (merged['alerta_plaga_actual'] != merged['alerta_plaga_historico'])
    ]
    
    return f"{len(cambios)} actualizadas de {len(df_actual)} totales"




# FUNCIÓN EJECUTAR ALERTAS

def add_alerts(df):

    df["alerta_helada"] = df.apply(riesgo_helada, axis=1)
    df["alerta_inundacion"] = df.apply(riesgo_inundacion, axis=1)
    df["alerta_plaga"] = df.apply(riesgo_plaga, axis=1)

    return df




def calcular_y_guardar_alertas():
    """Flujo completo para alertasTask"""
    logger.info("🌙 === ALERTAS 03:00 AM ===")
    
    try:
        # 1. Obtener datos meteo + calcular alertas
        dfDatosConAlertas = calcular_alertas()  # Tu función
        
        # 2. Procesar y guardar (histórico → UPSERT)
        procesar_y_guardar_alertas(dfDatosConAlertas)
        
    except Exception as e:
        logger.error(f"❌ Error procesando alertas: {e}")
        raise

calcular_y_guardar_alertas()

# Programar cada noche 03:00
schedule.every().day.at("03:00").do(calcular_y_guardar_alertas)


# Primera ejecución solo si ya son las 03:00 o después
if "03:00" in datetime.now().strftime("%H:%M"):
    calcular_alertas()

logger.info("AlertasTask iniciado - ejecutar a las 03:00 AM")

while True:
    schedule.run_pending()
    time.sleep(60)  # Revisa cada minuto (precisión 1 min)
