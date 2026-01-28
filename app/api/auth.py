import requests
import os
from flask import Blueprint, jsonify

auth_bp = Blueprint('auth', __name__, url_prefix='/agrosync-api')

def getToken():  # ← Ahora SÍ devuelve STRING
    userdata = {
        "username": os.getenv('AURAVANT_AUTH_USER', ''),
        "password": os.getenv('AURAVANT_AUTH_PASS', '')
    }

    #headers = {'SUBDOMAIN': os.getenv('SUBDOMAIN', ''), 'EXTENSION_ID': os.getenv('EXTENSION_ID', ''), 'SECRET': os.getenv('SECRET', '')}

    urlAuraAuth = os.getenv('AURAVANT_BASE_URL', 'https://api.auravant.com/api/') + 'auth'
    
    #resp = requests.post(urlAuraAuth, data=userdata, headers=headers)
    resp = requests.post(urlAuraAuth, data=userdata)
    if resp.status_code == 200:
        return resp.json().get("token")
    return None

@auth_bp.route('/authtoken', methods=['POST'])
def authtoken():
    token = getToken()
    if not token:
        return jsonify({"success": False, "message": "Credenciales inválidas"}), 401
    return jsonify({"success": True, "token": token}), 200
