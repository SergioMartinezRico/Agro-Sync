# app/ProgramedJobs/alertasTask.py
import sys
import os
import time
from datetime import datetime, timedelta

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


def calcular_alertas(id_parcela):
    """Calcula alertas nocturnas y guarda en BBDD"""
    logger.info("=== ALERTAS NOCTURNAS 05:00 AM ===")
    
    now = datetime.now()
    logger.info(f"Procesando datos hasta {now.strftime('%Y-%m-%d %H:%M')}")

    all_data = []

    parcelas = getParcelas4HistMeteo(id_parcela)

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


import pandas as pd
import numpy as np


def calculate_spi(precipitation_series, scale=30):
    spi_values = []
    for i in range(len(precipitation_series)):
        if i < scale:
            spi_values.append(np.nan)
        else:
            window = precipitation_series[i - scale:i]
            mean = np.mean(window)
            std = np.std(window)
            spi = (precipitation_series[i] - mean) / std if std > 0 else 0
            spi_values.append(spi)
    return spi_values


def process_climate(climate_df: pd.DataFrame) -> pd.DataFrame:
    # Asegurar tipos y orden
    climate_df['time'] = pd.to_datetime(climate_df['time'])
    climate_df = climate_df.sort_values(['field', 'time']).reset_index(drop=True)

    climate_outputs = []

    for field, field_data in climate_df.groupby('field'):
        field_data = field_data.sort_values('time').copy()

        # Rolling precipitation
        field_data['precip_30day_sum'] = (
            field_data['precipitation_sum']
            .rolling(window=30, min_periods=30)
            .sum()
        )

        field_data['precip_90day_sum'] = (
            field_data['precipitation_sum']
            .rolling(window=90, min_periods=90)
            .sum()
        )

        # Temperatura media diaria y rolling
        avg_temp_daily = (
            field_data['temperature_2m_max'] +
            field_data['temperature_2m_min']
        ) / 2

        field_data['temp_30day_avg'] = (
            avg_temp_daily
            .rolling(window=30, min_periods=30)
            .mean()
        )

        # SPI
        field_data['SPI_30'] = calculate_spi(
            field_data['precipitation_sum'].values,
            scale=30
        )

        # Sequía binaria desde SPI
        field_data['drought_binary_SPI'] = (field_data['SPI_30'] < -1).astype(int)

        # Severidad numérica SPI
        def drought_severity(spi):
            if pd.isna(spi):
                return 0
            elif spi >= -1.0:
                return 1   # Mild
            elif spi >= -1.5:
                return 2   # Moderate
            else:
                return 3   # Severe

        field_data['drought_severity'] = field_data['SPI_30'].apply(drought_severity)

        climate_outputs.append(field_data)

    climate_final = pd.concat(climate_outputs, ignore_index=True)
    return climate_final


def ndvi_based_drought(ndvi, gndvi, ndwi):
    if ndvi < 0.3:
        return 2   # Severe
    elif ndvi < 0.5:
        return 1   # Moderate
    else:
        return 0   # No drought


def process_soil(soil_df: pd.DataFrame) -> pd.DataFrame:
    soil_df['Fecha'] = pd.to_datetime(soil_df['Fecha'])

    soil_df['drought_soil_based'] = soil_df.apply(
        lambda row: ndvi_based_drought(row['NDVI'], row['GNDVI'], row['NDWI']),
        axis=1
    )
    soil_df['drought_binary_soil'] = (soil_df['drought_soil_based'] > 0).astype(int)

    return soil_df


def merge_climate_soil(climate_final: pd.DataFrame,
                       soil_df: pd.DataFrame) -> pd.DataFrame:
    merged_rows = []

    for field in climate_final['field'].unique():
        climate_field = climate_final[climate_final['field'] == field].copy()
        soil_field = soil_df[soil_df['Field'] == field].copy()

        for idx, row in climate_field.iterrows():
            date = row['time']
            soil_match = soil_field[
                abs((soil_field['Fecha'] - date).dt.days) <= 5
            ]

            if not soil_match.empty:
                closest_idx = abs(
                    (soil_match['Fecha'] - date).dt.days
                ).idxmin()
                soil_row = soil_field.loc[closest_idx]

                climate_field.loc[idx, 'drought_soil_based'] = soil_row['drought_soil_based']
                climate_field.loc[idx, 'drought_binary_soil'] = soil_row['drought_binary_soil']

        merged_rows.append(climate_field)

    all_predictions_merged = pd.concat(merged_rows, ignore_index=True)
    all_predictions_merged.fillna(method='ffill', inplace=True)

    return all_predictions_merged


def apply_final_drought_logic(all_predictions_merged: pd.DataFrame) -> pd.DataFrame:
    # Escalar severidad de suelo a escala clima
    soil_severity_mapping = {0: 0, 1: 2, 2: 3}

    all_predictions_merged['soil_severity_scaled'] = (
        all_predictions_merged['drought_soil_based']
        .map(soil_severity_mapping)
        .fillna(0)
    )

    # Severidad numérica final
    all_predictions_merged['severity_numeric'] = all_predictions_merged[
        ['drought_severity', 'soil_severity_scaled']
    ].max(axis=1)

    # Etiqueta de severidad
    def severity_label(value):
        if value <= 1:
            return 'Mild'
        elif value == 2:
            return 'Moderate'
        else:
            return 'Severe'

    all_predictions_merged['severity'] = all_predictions_merged[
        'severity_numeric'
    ].apply(severity_label)

    # Riesgo
    all_predictions_merged['drought_risk'] = np.where(
        (all_predictions_merged['drought_binary_SPI'] == 1) |
        (all_predictions_merged['drought_binary_soil'] == 1),
        'High',
        'Low'
    )

    # Confianza
    def drought_confidence(row):
        score = 0
        if row['drought_binary_SPI'] == 1:
            score += 40
        if row['drought_binary_soil'] == 1:
            score += 40
        if row['severity'] == 'Moderate':
            score += 10
        elif row['severity'] == 'Severe':
            score += 20
        return min(score, 100)

    all_predictions_merged['drought_confidence'] = all_predictions_merged.apply(
        drought_confidence, axis=1
    )

    return all_predictions_merged


def read_climate_from_db() -> pd.DataFrame:
    """Lee datos climáticos desde weather_archive"""
    query = '''
    SELECT 
        "time", 
        temp_max as "temperature_2m_max", 
        temp_min as "temperature_2m_min", 
        rain as "precipitation_sum", 
        humidity_mean as "humidity_mean", 
        humidity_min as "humidity_min", 
        humidity_max as "humidity_max", 
        uid_parcel as "field"
    FROM public.weather_archive
    ORDER BY uid_parcel, "time"
    '''
    
    climate_df = pd.read_sql(query, engine)
    climate_df['time'] = pd.to_datetime(climate_df['time'])
    
    print(f"🌦 {len(climate_df):,} filas climáticas cargadas desde BBDD")
    return climate_df


def read_soil_from_db() -> pd.DataFrame:
    """Lee índices de vegetación desde parcel_vegetation_indices"""
    query = '''
    SELECT 
        fecha as "Fecha",
        uid_parcel as "Field", 
        ndvi as "NDVI",
        gndvi as "GNDVI", 
        ndwi as "NDWI", 
        savi as "SAVI"
    FROM public.parcel_vegetation_indices
    ORDER BY uid_parcel, fecha
    '''
    
    soil_df = pd.read_sql(query, engine)
    soil_df['Fecha'] = pd.to_datetime(soil_df['Fecha'])
    
    print(f"🌿 {len(soil_df):,} filas de suelo cargadas desde BBDD")
    return soil_df

def calcular_alertas_sequia():
    print("\n🌱 Starting drought prediction pipeline...\n")

    # 1) Lectura CSV
    climate_df = read_climate_from_db()
    soil_df = read_soil_from_db()
    

    # 2) Clima
    print("🌦 Calculating rolling weather + drought indices...")
    climate_final = process_climate(climate_df)

    # 3) Suelo
    print("🌿 Processing soil drought indicators...")
    soil_df = process_soil(soil_df)

    # 4) Merge clima+suelo
    print("🔗 Merging climate and soil datasets...")
    all_predictions_merged = merge_climate_soil(climate_final, soil_df)

    # 5) Lógica final de sequía
    print("🧠 Computing final drought risk, severity and confidence...")
    all_predictions_merged = apply_final_drought_logic(all_predictions_merged)

    final_output = all_predictions_merged[
        [
            'time',
            'field',
            'precip_30day_sum',
            'precip_90day_sum',
            'temp_30day_avg',
            'drought_risk',
            'severity',
            'drought_confidence'
        ]
    ]

    print("\n✅ DONE!")
    return final_output
    


def procesar_y_guardar_alertas(dfDatosConAlertas):
    """1. Lee histórico → 2. UPSERT datos actuales → 3. Log cambios"""
    
    logger.info("🔄 Iniciando procesamiento de alertas...")
    
    # 1. CARGAR HISTÓRICO desde BBDD
    historic_query = """
    SELECT uid_parcel, fecha, alerta_helada, alerta_inundacion, alerta_plaga, alerta_sequia
    FROM alertas 
    WHERE fecha >= CURRENT_DATE - INTERVAL '7 days'
    """
    
    historicAlertaDataFrame = pd.read_sql(historic_query, engine)
    logger.info(f"📥 Histórico cargado: {len(historicAlertaDataFrame)} registros")
    
    # 2. PREPARAR DataFrame actual para BBDD
    #print(dfDatosConAlertas)
    df_alertas = dfDatosConAlertas[[
        'field', 'fecha', 'alerta_helada', 
        'alerta_inundacion', 'alerta_plaga', 'drought_risk'
    ]].copy()
    
    df_alertas.columns = ['uid_parcel', 'fecha', 'alerta_helada', 'alerta_inundacion', 'alerta_plaga', 'alerta_sequia']
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
        chunksize=1
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
            'alerta_plaga': insert_stmt.excluded.alerta_plaga,
            'alerta_sequia': insert_stmt.excluded.alerta_sequia
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


def merge_alertas_con_sequia(dfDatosConAlertas: pd.DataFrame, 
                           alertasSequia: pd.DataFrame) -> pd.DataFrame:
    """
    Fusiona alertas meteo + sequía por uid_parcel + fecha.
    Añade drought_risk a dfDatosConAlertas y nuevos registros de sequía.
    """
    
    # Normalizar nombres de columnas para merge
    dfDatosConAlertas = dfDatosConAlertas.copy()
    alertasSequia = alertasSequia.copy()
    
    # Renombrar columnas para merge consistente
    dfDatosConAlertas = dfDatosConAlertas.rename(columns={
        'date': 'fecha'
    })
    
    alertasSequia = alertasSequia.rename(columns={
        'time': 'fecha',
        'field': 'uid_parcel'
    })
    #print(dfDatosConAlertas)
    #print(alertasSequia)
    print(f"📊 Antes del merge:")
    print(f"  Alertas meteo: {len(dfDatosConAlertas)} filas")
    print(f"  Alertas sequía: {len(alertasSequia)} filas")
    
    # 1) Merge LEFT: alertas meteo + sequía (sequía opcional)
    df_merged = dfDatosConAlertas.merge(
        alertasSequia[['uid_parcel', 'fecha', 'drought_risk']],
        on=['uid_parcel', 'fecha'],
        how='left',
        suffixes=('', '_sequia')
    )
    
    # 2) Nuevos registros SOLO sequía (sin meteo previo)
    solo_sequia = alertasSequia[
        ~alertasSequia.set_index(['uid_parcel', 'fecha']).index
        .isin(dfDatosConAlertas.set_index(['uid_parcel', 'fecha']).index)
    ][['uid_parcel', 'fecha', 'drought_risk']]
    
    if not solo_sequia.empty:
        # Crear registros mínimos para solo sequía
        solo_sequia_minimal = solo_sequia.copy()
        solo_sequia_minimal['alerta_helada'] = None
        solo_sequia_minimal['alerta_inundacion'] = None
        solo_sequia_minimal['alerta_plaga'] = None
        df_merged = pd.concat([df_merged, solo_sequia_minimal], ignore_index=True)
        print(f"➕ Añadidos {len(solo_sequia)} registros solo sequía")
    
    # Restaurar nombres originales
    df_merged = df_merged.rename(columns={'uid_parcel': 'field'})
    
    # Reordenar columnas (meteo primero, sequía después)
    cols_orden = ['field', 'fecha'] + \
                 [col for col in df_merged.columns if col not in ['field', 'fecha', 'drought_risk']] + \
                 ['drought_risk']
    
    df_merged = df_merged[cols_orden]
    
    print(f"✅ Merge completado: {len(df_merged)} filas totales")
    print("\n🔍 Muestra del merge:")
    # print(df_merged[['field', 'fecha', 'rain', 'drought_risk']].head())
    
    return df_merged

def calcular_y_guardar_alertas(id_parcela):
    """Flujo completo para alertasTask"""
    logger.info("🌙 === ALERTAS 03:00 AM ===")
    
    try:
        # 1. Obtener datos meteo + calcular alertas
        dfDatosConAlertas = calcular_alertas(id_parcela)  
        print("📈 Alertas meteo:")
        #print(dfDatosConAlertas)
        
        
        # 2. Calcular alertas sequía
        alertasSequia = calcular_alertas_sequia()
        print("🌵 Alertas sequía:")
        #print(alertasSequia[['field', 'time', 'drought_risk']].head())
        
        # Fecha de hoy
        hoy = datetime.utcnow()

        # Fecha de hace 4 días
        hace_4_dias = hoy - timedelta(days=4)

        # Convertir a string en formato YYYY-MM-DD
        fecha_inicio = hace_4_dias.strftime('%Y-%m-%d')
        fecha_fin = hoy.strftime('%Y-%m-%d')

        # Crear el nuevo dataframe
        sequiaUltimos_dias = alertasSequia[
            (alertasSequia['time'] >= fecha_inicio) & 
            (alertasSequia['time'] <= fecha_fin)
        ].copy()

        
        # 3. FUSIÓN 
        dfFinalAlertas = merge_alertas_con_sequia(dfDatosConAlertas, sequiaUltimos_dias)
        #print(dfFinalAlertas)
        # 2. Procesar y guardar (histórico → UPSERT)

        columnas_alertas = ['alerta_helada', 'alerta_inundacion', 'alerta_plaga', 'drought_risk']

        dfFinalAlertas_limpio = dfFinalAlertas[
            dfFinalAlertas[columnas_alertas].notna().any(axis=1)
        ].copy()


        procesar_y_guardar_alertas(dfFinalAlertas_limpio)
        
    except Exception as e:
        logger.error(f"❌ Error procesando alertas: {e}")
        raise
