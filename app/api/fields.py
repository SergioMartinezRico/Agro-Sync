import requests
import os
from .auth import getToken  # ← Import específico
from flask import Blueprint, request, jsonify

field_bp = Blueprint('fields', __name__, url_prefix='/agrosync-api')

@field_bp.route('/getfields', methods=['POST'])  # ← GET, no POST
def getfields():
    token = getToken()
    if not token:
        return jsonify({"error": "No token"}), 401
        
    urlAuragetFields = os.getenv('AURAVANT_BASE_URL', 'https://api.auravant.com/api/') + 'getfields'
    headers = {'Authorization': f'Bearer {token}'}
    
    resp = requests.get(urlAuragetFields, headers=headers)  # ← GET
    
    return jsonify(resp.json()), resp.status_code


'''
CREA NUEVO LOTE
{
  "info": "Nuevo id lote 784125",
  "id_campo": 227760,
  "res": "ok",
  "uuid_lote": "19f19eed-21ad-450d-b390-a0a43031ebed",
  "id_lote": "784125",
  "uuid_campo": "7967bd23-59ae-4539-bfea-1a3591ee11a2"
}


DA ERROR PORQUE YA EXISTE:

{
  "info": "Ya existe un lote con ese nombre para el campo indicado",
  "res": "error",
  "code": 4
}

LA FINCA ES DEMASIADO GRANDE o INTERSECTA CON OTRA FINCA:

{
  "info": "Agotada cuota de ha",
  "res": "error",
  "code": 8
}

EL PRIMER VÉRTICE NO COINCIDE CON EL ÚLTIMO

{
  "code": 10,
  "info": "Polígono inválido",
  "res": "error"
}

'''

@field_bp.route('/agregarlote', methods=['POST']) 
def agregarlote():
    print("entro en agregarlote")
    token = getToken()
    if not token:
        return jsonify({"error": "No token"}), 401

    data = request.get_json()
    
    # Accede a los parámetros
    coordenadas = convertirArrayCoordenadasEnPoligono(data.get('shape'));
    print(coordenadas)
    nombreDeCampo = data.get('nombrecampo');

    urlAuragetFields = os.getenv('AURAVANT_BASE_URL', 'https://api.auravant.com/api/') + 'agregarlote'
    headers = {'Authorization': f'Bearer {token}'}
    userdata = {
        "nombre": -1,   
        "shape": coordenadas,
        "nombrecampo": nombreDeCampo
    }
    
    
    resp = requests.post(urlAuragetFields, headers=headers, data=userdata)  # ← GET
    
    return jsonify(resp.json()), resp.status_code



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


@field_bp.route('/eliminarlote', methods=['GET']) 
def eliminarlote():
    print("entro en eliminarlote")
    token = getToken()
    if not token:
        return jsonify({"error": "No token"}), 401

    idField = request.args.get('lote', 'default')
    
    urlAuragetFields = os.getenv('AURAVANT_BASE_URL', 'https://api.auravant.com/api/') + 'borrarlotes' + "?lote=" + idField
    headers = {'Authorization': f'Bearer {token}'}
    
    resp = requests.get(urlAuragetFields, headers=headers)
    
    return jsonify(resp.json()), resp.status_code