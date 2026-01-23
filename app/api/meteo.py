import requests
import pandas as pd
from flask import Blueprint, request, jsonify
from models.field import getParcelas4HistMeteo
import ast

meteo_bp = Blueprint('meteo', __name__, url_prefix='/agrosync-api')

@meteo_bp.route('/forecast', methods=['POST'])
def forecast():
    # TRAE EL ACTUAL SEGUN PARÁMETROS DE ENTRADA DE LONGITUD Y LATITUD
    print("entro en forecast")
    data = request.get_json()
    lat = data.get('lat')
    lon = data.get('lon')
    return getForcasByLatLong(lat, lon)    


def getForcasByLatLong(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,cloud_cover,wind_speed_10m,wind_direction_10m",
        "timezone": "auto"
    }

    r = requests.get(url, params=params)
    r.raise_for_status()
    data = r.json()

    cur = data["current"]

    # Construimos dict directamente (no hace falta DataFrame)
    forecast = {
        'tiempo': pd.to_datetime(cur["time"]).isoformat(),
        "precipitacion": cur["precipitation"],
        "temperatura": cur["temperature_2m"],
        "humedad": cur["relative_humidity_2m"],
        "nubosidad": cur["cloud_cover"],
        "viento": {
            "velocidad": cur["wind_speed_10m"],
            "direccion": cur["wind_direction_10m"]
        },
        "fecha": pd.to_datetime(cur["time"]).isoformat()
    }

    return {
        "forecast": forecast
    }


# FUNCIÓN TIMEPO A 7 DÍAS + FEATURES PARA ALERTAS
@meteo_bp.route('/forecast_nextweek', methods=['POST'])
def forecast_nextweek():
    
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
    print(df_all)    
    dfDatosConAlertas = add_alerts(df_all)
    print(dfDatosConAlertas.columns)
    print("dfDatosConAlertas: ")
    print(dfDatosConAlertas)
    data = dfDatosConAlertas.copy()
    data["date"] = data["date"].astype(str)

    json_data = data.to_dict(orient="records")
    return json_data


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

# FUNCIÓN EJECUTAR ALERTAS

def add_alerts(df):

    df["alerta_helada"] = df.apply(riesgo_helada, axis=1)
    df["alerta_inundacion"] = df.apply(riesgo_inundacion, axis=1)
    df["alerta_plaga"] = df.apply(riesgo_plaga, axis=1)

    return df