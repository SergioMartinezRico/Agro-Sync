from flask import Flask
from flask_cors import CORS
from app.api.auth import auth_bp
from app.api.fields import field_bp
from app.api.meteo import meteo_bp
from app.api.maps import sentinel_bp
from app.api.conversations import conversations_bp
from app.api.app_llm import messages_bp

app = Flask(__name__)
#CORS(app)  # ← ESTO HACE LA MAGIA ✨
CORS(app, resources={r"/*": {"origins": "*"}})
CORS(app, resources={r"/*": {
            "origins": "*",
            "allow_headers": "*"
        }})

# Registrar blueprint
app.register_blueprint(auth_bp)
app.register_blueprint(field_bp)
app.register_blueprint(meteo_bp)
app.register_blueprint(sentinel_bp)
app.register_blueprint(conversations_bp)
app.register_blueprint(messages_bp)

@app.route('/')
def home():
    return {
        "service": "AgroSync API v24",
        "endpoints": [
            # AUTENTICACIÓN
            {
                "path": "/agrosync-api/authtoken",
                "method": "POST", 
                "auth_required": False,
                "description": "Token Bearer Auravant (SUBDOMAIN/EXTENSION_ID/SECRET)"
            },
            # CAMPOS AURAVANT
            {
                "path": "/agrosync-api/getfields",
                "method": "POST",
                "auth_required": True,
                "description": "Lista completa campos usuario autenticado"
            },
            {
                "path": "/agrosync-api/agregarlote",
                "method": "POST",
                "auth_required": True,
                "body": {"nombrecampo": "string", "shape": "[[lat,lon]]"},
                "description": "Crea lote POLYGON WKT (errores: code 4,8,10)"
            },
            {
                "path": "/agrosync-api/eliminarlote?lote=ID",
                "method": "GET",
                "auth_required": True,
                "description": "Borra lote por ID"
            },
            # METEO
            {
                "path": "/agrosync-api/forecast",
                "method": "POST",
                "auth_required": False,
                "body": {"lat": "float", "lon": "float"},
                "description": "Open-Meteo actual (temp/humedad/precip/viento)"
            },
            {
                "path": "/agrosync-api/forecastnextweek",  # ← ¡EL FALTANTE!
                "method": "POST",
                "auth_required": False,
                "description": "7 días TODAS parcelas PostgreSQL + alertas (helada/inundación/plaga)"
            },
            # ANÁLISIS IA
            {
                "path": "/agrosync-api/analyze?idparcela=ID",
                "method": "POST",
                "auth_required": False,
                "body": {"image": "file"},
                "description": "AgroEngine 3D (sky/soil/crop) + forecast parcela"
            },
            {
                "path": "/agrosync-api/plant/health",
                "method": "GET",
                "auth_required": False,
                "description": "Estado AgroEngine (engine_loaded)"
            },
            # SATELITE
            {
                "path": "/agrosync-api/maps_sentinel",
                "method": "POST",
                "auth_required": False,
                "body": {"uid_parcel": "string"},
                "description": "Sentinel-2 NDVI/NDWI/NDRE/GNDVI mapas base64. Solo hay que mandar el parámetro uid_parcel con el Id de la parcela de la base de datos."
            }
        ]
    }



if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8282, debug=True)
