from flask import Blueprint, request, jsonify
from .sentinel_service import SentinelService

# Creamos el Blueprint
sentinel_bp = Blueprint('sentinel_bp', __name__)

@sentinel_bp.route('/maps_sentinel', methods=['POST'])
def analyze_field():
    """
    Endpoint principal.
    Espera un JSON con la estructura:
    {
        "uid_parcel": "Nombre_Finca",
        "wkt": "POLYGON((...))"
    }
    """
    try:
        # 1. Recibir los datos (El "Body" de la petición)
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No se recibieron datos JSON"}), 400
            
        finca_id = data.get('uid_parcel')
        wkt_polygon = data.get('wkt')

        # 2. Validaciones básicas
        if not wkt_polygon:
            return jsonify({"error": "Falta el campo 'wkt' con la geometría"}), 400

        # 3. Invocar al Servicio (El experto)
        service = SentinelService()
        result = service.analyze_polygon(wkt_polygon)

        if not result:
            return jsonify({"error": "No se pudieron obtener imágenes recientes o válidas"}), 404

        # 4. Añadir el ID al resultado final para mantener la trazabilidad
        result["uid_parcel"] = finca_id
        
        return jsonify(result), 200

    except Exception as e:
        # En producción, aquí deberíamos hacer logging del error real
        return jsonify({"error": f"Error interno del servidor: {str(e)}"}), 500