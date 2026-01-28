import schedule
import time
import pandas as pd
import logging
import ast

from psycopg2.extras import RealDictCursor

import psycopg2
import os
from dotenv import load_dotenv


import time
from datetime import datetime

import ee, json
from shapely import wkt

from datetime import datetime, timedelta

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

def convertirArrayCoordenadasEnPoligono(coords):
    """
    Convierte [[lat1, lon1], [lat2, lon2], ...] a 'POLYGON((lon1 lat1, lon2 lat2, ...))'
    
    Args:
        coords: list de [lat, lon] como lo recibe de fullstack
    
    Returns:
        str en formato WKT para Auravant API
    """
    if not coords or len(coords) < 3:
        raise ValueError("El polígono necesita al menos 3 coordenadas")
    
    # Extrae lon lat (invierte orden) y formatea
    pairs = [f"{lon} {lat}" for lat, lon in coords]
    
    # Asegura cierre (primer punto == último)
    if pairs[0] != pairs[-1]:
        pairs.append(pairs[0])
    
    return f"POLYGON(({', '.join(pairs)}))"


def save_indices_to_db(df: pd.DataFrame):
    """
    Inserta el DataFrame en la tabla parcel_vegetation_indices.
    Solo inserta un registro si no existe exactamente la misma fila.
    """

    if df.empty:
        logger.info("⚠️ DataFrame vacío. Nada que insertar.")
        return

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:

            insert_sql = """
                INSERT INTO parcel_vegetation_indices (uid_parcel, fecha, ndvi, gndvi, ndwi, savi)
                SELECT %s, %s, %s, %s, %s, %s
                WHERE NOT EXISTS (
                    SELECT 1 FROM parcel_vegetation_indices
                    WHERE uid_parcel = %s
                      AND fecha = %s
                      AND ndvi = %s
                      AND gndvi = %s
                      AND ndwi = %s
                      AND savi = %s
                );
            """

            values = [
                (
                    row['Field'], row['Fecha'], row['NDVI'], row['GNDVI'], row['NDWI'], row['SAVI'],  # para INSERT
                    row['Field'], row['Fecha'], row['NDVI'], row['GNDVI'], row['NDWI'], row['SAVI']   # para WHERE NOT EXISTS
                )
                for _, row in df.iterrows()
            ]

            cur.executemany(insert_sql, values)
            conn.commit()

            logger.info(f"✅ Insertadas {cur.rowcount} filas en parcel_vegetation_indices (sin duplicados exactos)")

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Error insertando índices en DB: {e}")

    finally:
        conn.close()




# --------------------------------------------------
# 1) INICIALIZAR GOOGLE EARTH ENGINE
# --------------------------------------------------
def leerYGuardarVegetacionIndices(id_parcela=None):
    CREDENTIALS_PATH = '/app/app/api/creds/desafio-tripulaciones-484914-d7647b47c61b.json'  # Tu archivo descargado
    # CREDENTIALS_PATH = '/app/app/ProgramedJobs/creds/desafio-tripulaciones-484914-d7647b47c61b.json'  # Tu archivo descargado
    PROYECTO_ID = 'desafio-tripulaciones-484914'
    try:
        print("🔑 Cargando credenciales service account...")
        print("credential path: ", CREDENTIALS_PATH)
        # Verificar que el archivo existe
        if not os.path.exists(CREDENTIALS_PATH):
            raise FileNotFoundError(f"❌ JSON no encontrado: {CREDENTIALS_PATH}")
        
        # Cargar JSON y verificar client_email
        with open(CREDENTIALS_PATH, 'r') as f:
            credentials_info = json.load(f)
        
        service_account = credentials_info['client_email']
        print(f"✅ Service Account: {service_account}")
        
        # Inicializar con PROYECTO y credenciales
        credentials = ee.ServiceAccountCredentials(service_account, CREDENTIALS_PATH)
        ee.Initialize(
            credentials=credentials,
            project=PROYECTO_ID 
        )
        
        print("🎉 Earth Engine inicializado correctamente SIN browser!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        raise

    # --------------------------------------------------
    # 2) FINCAS (WKT)
    # --------------------------------------------------
    
    parcelasDB = getParcelas4HistMeteo(id_parcela);
    parcelasTratadas = {}
    for row in parcelasDB:
        uid = row["uid_parcel"]
        coords = row["coordinates_parcel"]
        coords_list = ast.literal_eval(coords)
        wktCoords = convertirArrayCoordenadasEnPoligono(coords_list)
        parcelasTratadas[uid] = wktCoords



    # --------------------------------------------------
    # 3) WKT → FEATURECOLLECTION
    # --------------------------------------------------
    features = []
    for name, geom_wkt in parcelasTratadas.items():
        geom = ee.Geometry(wkt.loads(geom_wkt).__geo_interface__)
        features.append(ee.Feature(geom, {'Field': name}))

    fincas_fc = ee.FeatureCollection(features)

    # --------------------------------------------------
    # 4) ÍNDICES
    # --------------------------------------------------
    def add_indices(img):
        ndvi = img.normalizedDifference(['B8', 'B4']).rename('NDVI')
        gndvi = img.normalizedDifference(['B8', 'B3']).rename('GNDVI')
        ndwi = img.normalizedDifference(['B3', 'B8']).rename('NDWI')

        savi = img.expression(
            '((NIR - RED) / (NIR + RED + 0.5)) * 1.5',
            {'NIR': img.select('B8'), 'RED': img.select('B4')}
        ).rename('SAVI')

        return img.addBands([ndvi, gndvi, ndwi, savi])

    # --------------------------------------------------
    # 5) SENTINEL-2
    # --------------------------------------------------

    # Fecha de hoy
    hoy = datetime.utcnow()

    # Fecha de hace 4 días
    hace_60_dias = hoy - timedelta(days=60)

    # Convertir a string en formato YYYY-MM-DD
    fecha_inicio = hace_60_dias.strftime('%Y-%m-%d')
    fecha_fin = hoy.strftime('%Y-%m-%d')

    s2 = (
        ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterBounds(fincas_fc)                    # ← ZONA GEOGRÁFICA primero
        .filterDate(fecha_inicio, fecha_fin)     
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
        .map(add_indices)
    )

    print(f"🔍 {s2.size().getInfo()} imágenes encontradas")


    # --------------------------------------------------
    # 6) EXTRAER VALORES
    # --------------------------------------------------
    def extract(img):
        date = img.date().format('yyyy-MM-dd')
        fc = img.select(['NDVI', 'GNDVI', 'NDWI', 'SAVI']).reduceRegions(
            collection=fincas_fc,
            reducer=ee.Reducer.mean(),
            scale=10
        )
        return fc.map(lambda f: f.set('Fecha', date))

    results = s2.map(extract).flatten().filter(
        ee.Filter.notNull(['NDVI'])
    )

    # --------------------------------------------------
    # 7) A CSV
    # --------------------------------------------------
    print("Descargando datos desde Google Earth Engine...")
    data = results.getInfo()

    rows = []
    for f in data['features']:
        p = f['properties']
        rows.append({
            'Fecha': p['Fecha'],
            'Field': p['Field'],
            'NDVI': p['NDVI'],
            'GNDVI': p['GNDVI'],
            'NDWI': p['NDWI'],
            'SAVI': p['SAVI']
        })

    df = pd.DataFrame(rows)
    
    '''
    df.to_csv('indices_fincas_S3.csv', index=False)

    print("✅ CSV generado correctamente:", df.shape)
    '''
    
    save_indices_to_db(df)

    print("✅ Datos guardados en base de datos correctamente:", df.shape)


