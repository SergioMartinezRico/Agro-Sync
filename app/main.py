from flask import Flask
from flask_cors import CORS
from app.api.auth import auth_bp
from app.api.fields import field_bp
from app.api.plant import plant_bp
from app.api.meteo import meteo_bp

app = Flask(__name__)
CORS(app)  # ← ESTO HACE LA MAGIA ✨

# Registrar blueprint
app.register_blueprint(auth_bp)
app.register_blueprint(field_bp)
app.register_blueprint(meteo_bp)
app.register_blueprint(plant_bp)

@app.route('/')
def home():
    return {
        "service": "AgroSync API",
        "version": "v11",
        "description": "API de integración con Auravant, servicios meteorológicos y motor AgroEngine",
        "base_url": "http://localhost:8282/agrosync-api",
        "authentication": {
            "type": "Bearer Token",
            "provider": "Auravant",
            "endpoint": "/agrosync-api/authtoken"
        },
        "endpoints": [
            {
                "path": "/agrosync-api/authtoken",
                "method": "POST",
                "auth_required": False,
                "description": "Obtiene token de autenticación contra Auravant",
                "headers": {
                    "SUBDOMAIN": "string",
                    "EXTENSION_ID": "string",
                    "SECRET": "string"
                },
                "response": {
                    "success": "boolean",
                    "token": "string"
                }
            },
            {
                "path": "/agrosync-api/getfields",
                "method": "POST",
                "auth_required": True,
                "description": "Obtiene la lista de campos del usuario desde Auravant",
                "external_api": "Auravant getfields"
            },
            {
                "path": "/agrosync-api/agregarlote",
                "method": "POST",
                "auth_required": True,
                "description": "Crea un nuevo lote en un campo de Auravant",
                "body": {
                    "nombrecampo": "string",
                    "shape": "[[lat, lon], [lat, lon], ...]  // array de coordenadas lat/lon que se convierten a POLYGON WKT"
                },
                "external_api": "Auravant agregarlote"
            },
            {
                "path": "/agrosync-api/eliminarlote",
                "method": "GET",
                "auth_required": True,
                "query_params": {
                    "lote": "ID del lote"
                },
                "description": "Elimina un lote existente en Auravant",
                "external_api": "Auravant borrarlotes"
            },
            {
                "path": "/agrosync-api/forecast",
                "method": "POST",
                "auth_required": False,
                "description": "Obtiene condiciones meteorológicas actuales para una lat/lon",
                "body": {
                    "lat": "float",
                    "lon": "float"
                },
                "response": {
                    "temperatura": "float",
                    "humedad": "float",
                    "precipitacion": "float",
                    "nubosidad": "float",
                    "viento": {
                        "velocidad": "float",
                        "direccion": "float"
                    },
                    "fecha": "string (ISO8601)"
                },
                "external_api": "Open-Meteo current forecast"
            },
            {
                "path": "/agrosync-api/forecastnextweek",
                "method": "POST",
                "auth_required": False,
                "description": "Obtiene pronóstico a 7 días para todas las parcelas con features y alertas de riesgo",
                "response": {
                    "uidparcel": "string",
                    "date": "string (ISO8601)",
                    "tempmax": "float",
                    "tempmin": "float",
                    "tempmean": "float",
                    "rain": "float",
                    "humiditymax": "float",
                    "humiditymin": "float",
                    "humiditymean": "float",
                    "rain3dsum": "float",
                    "rain7dsum": "float",
                    "humidity3dmean": "float",
                    "temp7dmean": "float",
                    "alerta_helada": "ALTO | MEDIO | null",
                    "alerta_inundacion": "ALTO | MEDIO | null",
                    "alerta_plaga": "ALTO | MEDIO | null"
                },
                "external_api": "Open-Meteo 7-day forecast + motor de alertas interno"
            },
            {
                "path": "/agrosync-api/analyze",
                "method": "POST",
                "auth_required": False,
                "description": "Analiza una imagen de cultivo con AgroEngine e incorpora el forecast actual de la parcela",
                "query_params": {
                    "idparcela": "ID de la parcela a analizar"
                },
                "body": {
                    "image": "file (multipart/form-data)"
                },
                "response": {
                    "status": "success | error",
                    "source": "plantmodule",
                    "data": "resultados del motor AgroEngine",
                    "forcast": "objeto de current forecast (misma estructura que /forecast)"
                },
                "external_modules": [
                    "AgroEngine",
                    "Open-Meteo current forecast",
                    "models.field.getParcelas4HistMeteo"
                ]
            },
            {
                "path": "/agrosync-api/plant/health",
                "method": "GET",
                "auth_required": False,
                "description": "Healthcheck del módulo plant.py",
                "response": {
                    "module": "plant.py",
                    "status": "active",
                    "engineloaded": "boolean"
                }
            }
        ]
    }


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8282, debug=True)
