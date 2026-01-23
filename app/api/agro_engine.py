import cv2
import json
import numpy as np
import requests
import math
import os
from roboflow import Roboflow
from flask import Blueprint, jsonify

# --- CONFIGURACIÓN ---
ROBOFLOW_API_KEY = "Meni7XPRgKOEkHJeXRHz"

class AgroEngine:
    def __init__(self):
        # Solo inicializamos Roboflow
        self.rf = Roboflow(api_key=ROBOFLOW_API_KEY)
        self.project = self.rf.workspace("agridrone-pblcc").project("agridetect")
        self.version = self.project.version(3)
        self.model = self.version.model

    def _decode_bytes_to_numpy(self, image_bytes):
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            return img
        except Exception:
            return None

    def _pixel_to_unit_vector_dual_fisheye(self, x, y, width, height):
        """
        Calcula el vector 3D unitario para cámaras Dual Fisheye (Insta360).
        """
        lens_width = width / 2
        lens_radius = height / 2 
        
        is_front_lens = True
        center_x = 0
        center_y = height / 2
        
        if x < lens_width:
            is_front_lens = True
            center_x = lens_width / 2
        else:
            is_front_lens = False
            center_x = lens_width + (lens_width / 2)

        u = (x - center_x) / lens_radius
        v = (y - center_y) / lens_radius

        distance_sq = u*u + v*v
        if distance_sq > 1.0:
            return None 

        z_component = math.sqrt(max(0, 1.0 - distance_sq))

        vec_x = u
        vec_y = -v 
        
        if is_front_lens:
            vec_z = z_component 
        else:
            vec_z = -z_component
            vec_x = -vec_x 

        return {
            "x": round(vec_x, 4), 
            "y": round(vec_y, 4), 
            "z": round(vec_z, 4)
        }

    def _process_roboflow_hybrid(self, image_numpy):
        try:
            if image_numpy is None:
                return {"error": "Imagen no válida para Roboflow"}

            height, width, _ = image_numpy.shape
            img_rgb = cv2.cvtColor(image_numpy, cv2.COLOR_BGR2RGB)

            # Inferencia Roboflow
            response = self.model.predict(img_rgb, confidence=5).json()

            detections = []
            if isinstance(response, dict) and 'predictions' in response:
                detections = response['predictions']
            elif isinstance(response, list):
                detections = response
            
            # --- Procesamiento SUELO ---
            soil_labels = ["field-soil", "unused-land", "agriculture-land", "trees", "crop", "soil", "land"]
            best_soil = None
            max_conf_soil = 0

            for det in detections:
                if det['class'] in soil_labels:
                    if det['confidence'] > max_conf_soil:
                        max_conf_soil = det['confidence']
                        best_soil = det
            
            soil_result = None
            if best_soil:
                cx, cy = best_soil['x'], best_soil['y']
                vector_3d = self._pixel_to_unit_vector_dual_fisheye(cx, cy, width, height)
                
                # Fallback vectorial si cae en zona muerta
                if vector_3d is None:
                    vector_3d = {"x": 0, "y": -0.5, "z": 0.866}

                soil_result = {
                    "pixel_coords": {"x": int(cx), "y": int(cy)},
                    "vector_3d": vector_3d,
                    "source": "IA",
                    "confidence": best_soil['confidence']
                }
            else:
                # Fallback Geométrico (Hardcoded)
                cx, cy = width / 4, height * 0.75
                soil_result = {
                    "pixel_coords": {"x": int(cx), "y": int(cy)},
                    "vector_3d": {"x": 0.0, "y": -0.7071, "z": 0.7071}, 
                    "source": "FALLBACK_GEOMETRY"
                }

            # --- Procesamiento CIELO ---
            sky_labels = ["sky", "cielo", "cloud"]
            best_sky = None
            max_conf_sky = 0

            for det in detections:
                if det['class'] in sky_labels:
                    if det['confidence'] > max_conf_sky:
                        max_conf_sky = det['confidence']
                        best_sky = det
            
            sky_result = None
            if best_sky:
                cx, cy = best_sky['x'], best_sky['y']
                vector_3d = self._pixel_to_unit_vector_dual_fisheye(cx, cy, width, height)
                
                if vector_3d is None:
                     vector_3d = {"x": 0, "y": 0.5, "z": 0.866}

                sky_result = {
                    "pixel_coords": {"x": int(cx), "y": int(cy)},
                    "vector_3d": vector_3d,
                    "source": "IA",
                    "confidence": best_sky['confidence']
                }
            else:
                # Fallback Geométrico
                cx, cy = width / 4, height * 0.25
                sky_result = {
                    "pixel_coords": {"x": int(cx), "y": int(cy)},
                    "vector_3d": {"x": 0.0, "y": 0.7071, "z": 0.7071},
                    "source": "FALLBACK_GEOMETRY"
                }

            return {
                "sky": sky_result,
                "soil": soil_result
            }

        except Exception as e:
            return {"error": f"Fallo en Roboflow Hybrid: {str(e)}"}

    def download_image_from_url(self, url):
        """Descarga la imagen de la URL y devuelve bytes"""
        print(f"Descargando imagen desde: {url} ...")
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            print("-> Descarga completada.")
            return response.content
        except Exception as e:
            print(f"[ERROR DE RED] {e}")
            return None

    def analyze_full(self, raw_image_bytes):
        # 1. Decodificar
        image_numpy = self._decode_bytes_to_numpy(raw_image_bytes)
        if image_numpy is None: return {"error": "Archivo corrupto o no es imagen"}
        
        # 2. Procesar Geometría y Zonas (Roboflow + Matemáticas)
        roi_data = self._process_roboflow_hybrid(image_numpy)
        
        # Retornamos estructura simplificada
        return {"telemetry_roi": roi_data}

# --- BLOQUE DE EJECUCIÓN ---
if __name__ == "__main__":
    
    # URL de prueba
    TEST_URL = "https://res.cloudinary.com/dbi5thf23/image/upload/v1769162534/IMG_20240927_115037_00_107_1_3_cd3cph.jpg" 
    
    print("--- MOTOR DE TELEMETRÍA (SIN BIOLOGÍA) ---")
    
    engine = AgroEngine()
    
    # 1. Descargar
    file_bytes = engine.download_image_from_url(TEST_URL)
    
    if file_bytes:
        # 2. Analizar
        print("Analizando geometría...")
        resultado = engine.analyze_full(file_bytes)
        
        print("\n--- RESULTADO FINAL ---")
        print(json.dumps(resultado, indent=4))
    else:
        print("No se pudo procesar porque la descarga falló.")