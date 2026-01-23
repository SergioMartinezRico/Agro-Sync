import cv2
import numpy as np
import math
from roboflow import Roboflow
import traceback

# --- CONFIGURACIÓN ---
ROBOFLOW_API_KEY = "Meni7XPRgKOEkHJeXRHz"
MIRROR_BACK_LENS = True 

class AgroEngine:
    def __init__(self):
        print("⚙️ [AgroEngine] Cargando modelo Roboflow...")
        self.rf = Roboflow(api_key=ROBOFLOW_API_KEY)
        self.project = self.rf.workspace("agridrone-pblcc").project("agridetect")
        self.version = self.project.version(3)
        self.model = self.version.model
        print("✅ [AgroEngine] Modelo cargado.")

    def _decode_bytes_to_numpy(self, image_bytes):
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            return img
        except Exception as e:
            print(f"❌ Error decodificando: {e}")
            return None

    # --- 1. LÓGICA DE CENTROIDE INTELIGENTE (V8 - LOGICA USUARIO) ---
    def _find_green_centroid_smart(self, img_full, x_box, y_box, w_box, h_box):
        """
        ESTRATEGIA V8:
        1. Mira el centro de la caja. ¿Es verde? -> Úsalo.
        2. ¿No es verde (ej: persona)? -> Busca la masa verde más grande dentro de la caja.
        Devuelve: (x, y, status_string)
        """
        try:
            # 1. Definir ROI
            h_img, w_img, _ = img_full.shape
            y_start = max(0, int(y_box - h_box/2))
            y_end   = min(h_img, int(y_box + h_box/2))
            x_start = max(0, int(x_box - w_box/2))
            x_end   = min(w_img, int(x_box + w_box/2))
            
            roi = img_full[y_start:y_end, x_start:x_end]
            if roi.size == 0: return int(x_box), int(y_box), "ERR-ROI"

            # 2. Preparar análisis de color
            roi_blur = cv2.GaussianBlur(roi, (5, 5), 0)
            hsv_roi = cv2.cvtColor(roi_blur, cv2.COLOR_BGR2HSV)
            lower_green = np.array([30, 40, 40])
            upper_green = np.array([90, 255, 255])

            # --- ESTRATEGIA 1: PROBAR EL CENTRO GEOMÉTRICO ---
            # Si el centro de la caja ya es verde, no nos compliquemos.
            center_y_local = int(roi.shape[0] / 2)
            center_x_local = int(roi.shape[1] / 2)
            
            # Tomamos una muestra pequeña del centro (5x5 px)
            # Aseguramos límites para no salirnos del array
            y_sample_start = max(0, center_y_local-2)
            y_sample_end = min(roi.shape[0], center_y_local+2)
            x_sample_start = max(0, center_x_local-2)
            x_sample_end = min(roi.shape[1], center_x_local+2)

            sample = hsv_roi[y_sample_start:y_sample_end, x_sample_start:x_sample_end]
            
            if sample.size > 0:
                mask_sample = cv2.inRange(sample, lower_green, upper_green)
                # Si más del 50% de la muestra central es verde, aceptamos el centro
                if cv2.countNonZero(mask_sample) > (sample.size * 0.5):
                    return int(x_box), int(y_box), "CENTER-OK"

            # --- ESTRATEGIA 2: BUSCAR MASA VERDE (FALLBACK) ---
            # Si llegamos aquí, el centro NO era verde. Buscamos mancha verde.
            mask = cv2.inRange(hsv_roi, lower_green, upper_green)
            kernel = np.ones((5,5), np.uint8)
            mask_clean = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)
            
            contours, _ = cv2.findContours(mask_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if contours:
                largest_contour = max(contours, key=cv2.contourArea)
                
                # Filtro de seguridad (tamaño mínimo 50px)
                if cv2.contourArea(largest_contour) > 50:
                    M = cv2.moments(largest_contour)
                    if M["m00"] != 0:
                        cX_local = int(M["m10"] / M["m00"])
                        cY_local = int(M["m01"] / M["m00"])
                        return int(x_start + cX_local), int(y_start + cY_local), "MOVED-TO-GREEN"

            # Si todo falla, devolvemos centro original
            return int(x_box), int(y_box), "NO-GREEN-FOUND"

        except Exception as e:
            print(f"⚠️ Error en Smart Centroid: {e}")
            return int(x_box), int(y_box), "ERR-EXC"

    def _detect_sky_hsv(self, img_cv2):
        """Respaldo para detectar cielo si la IA falla"""
        try:
            hsv = cv2.cvtColor(img_cv2, cv2.COLOR_BGR2HSV)
            h, w, _ = img_cv2.shape
            mask = cv2.inRange(hsv, np.array([85, 30, 100]), np.array([135, 255, 255]))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5,5), np.uint8))
            mask[int(h*0.5):, :] = 0 
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contours = sorted(contours, key=cv2.contourArea, reverse=True)
            for cnt in contours:
                if cv2.contourArea(cnt) > 3000:
                    x, y, w_rect, h_rect = cv2.boundingRect(cnt)
                    return [{'class': 'sky-fallback', 'confidence': 0.99, 'x': x+w_rect/2, 'y': y+h_rect/2, 'width': w_rect, 'height': h_rect}]
            return []
        except:
            return []

    # --- MATEMÁTICA 3D ---
    def _pixel_to_unit_vector_dual_fisheye(self, x, y, width, height):
        lens_width = width / 2
        lens_radius = height / 2 
        
        if x < lens_width:
            is_front_lens = True
            center_x = lens_width / 2
        else:
            is_front_lens = False
            center_x = lens_width + (lens_width / 2)

        center_y = height / 2
        u = (x - center_x) / lens_radius
        v = (y - center_y) / lens_radius
        distance_sq = u*u + v*v
        
        if distance_sq > 1.0: return None 

        z_component = math.sqrt(max(0, 1.0 - distance_sq))
        vec_x = u
        vec_y = -v 
        
        if is_front_lens:
            vec_z = z_component 
        else:
            vec_z = -z_component
            if MIRROR_BACK_LENS: vec_x = -vec_x

        return {"x": round(vec_x, 4), "y": round(vec_y, 4), "z": round(vec_z, 4)}

    def _convert_to_aframe_vector(self, vector_math, radius=10):
        if vector_math is None: return None
        return {
            "x": round(vector_math['x'] * radius, 4),
            "y": round(vector_math['y'] * radius, 4),
            "z": round(vector_math['z'] * -1 * radius, 4)
        }

    # --- LÓGICA PRINCIPAL (HÍBRIDA) ---
    def _process_roboflow_hybrid(self, image_numpy):
        try:
            if image_numpy is None: return {"error": "Imagen no válida"}
            height, width, _ = image_numpy.shape
            img_rgb = cv2.cvtColor(image_numpy, cv2.COLOR_BGR2RGB)

            # 1. DETECCIÓN PERMISIVA (Confidence 1%)
            response = self.model.predict(img_rgb, confidence=1).json()
            detections = response['predictions'] if 'predictions' in response else []

            # 2. Respaldo de cielo
            if not any(d['class'] in ["sky", "cielo", "cloud"] for d in detections):
                detections.extend(self._detect_sky_hsv(image_numpy))

            # 3. Clasificación Robusta
            sky_labels = ["sky", "cielo", "cloud", "clouds", "sky-fallback"]
            soil_labels = ["field-soil", "unused-land", "soil", "land", "ground", "dirt"]
            
            cat_results = {
                "sky": {"det": None, "max_conf": 0, "fallback_vec": {"x": 0.0, "y": 0.7071, "z": 0.7071}},
                "soil": {"det": None, "max_conf": 0, "fallback_vec": {"x": 0.0, "y": -0.8, "z": 0.6}},
                "crop": {"det": None, "max_conf": 0, "fallback_vec": {"x": 0.0, "y": -0.5, "z": 0.866}}
            }

            for det in detections:
                cls = det['class'].lower()
                conf = det['confidence']
                
                target_cat = "crop" # Por defecto es crop
                if cls in sky_labels: target_cat = "sky"
                elif cls in soil_labels: target_cat = "soil"
                
                if conf > cat_results[target_cat]["max_conf"]:
                    cat_results[target_cat]["max_conf"] = conf
                    cat_results[target_cat]["det"] = det

            # 4. Calcular Vectores y Centroides
            final_results = {}
            for cat_name, data in cat_results.items():
                best_det = data["det"]
                px, py = 0, 0
                vector_3d = None
                source = "FALLBACK"
                confidence = 0

                if best_det:
                    source = "IA"
                    confidence = best_det['confidence']
                    
                    if cat_name == "crop":
                        # --- APLICAMOS LÓGICA V8 ---
                        # Usamos la función inteligente que decide si usar centro o buscar verde
                        px, py, status = self._find_green_centroid_smart(
                            image_numpy, 
                            best_det['x'], best_det['y'], 
                            best_det['width'], best_det['height']
                        )
                        # Modificamos el source para reflejar qué decisión tomó (ej: IA-MOVED-TO-GREEN)
                        source = f"IA-{status}"
                    else:
                        px, py = int(best_det['x']), int(best_det['y'])
                        if confidence == 0.99 and cat_name == "sky": source = "HSV-CV"

                    vector_3d = self._pixel_to_unit_vector_dual_fisheye(px, py, width, height)

                # Fallbacks de vector
                if vector_3d is None:
                    vector_3d = data["fallback_vec"]
                    if "FALLBACK" not in source: source += "-OUT-OF-LENS"
                
                final_results[cat_name] = {
                    "detected": (confidence > 0),
                    "source": source,
                    "confidence": confidence,
                    "pixel_coords": {"x": px, "y": py},
                    "aframe_position": self._convert_to_aframe_vector(vector_3d, radius=10)
                }
            
            return final_results

        except Exception as e:
            print(f"❌ Error CRÍTICO en process: {e}")
            traceback.print_exc()
            return {"error": str(e)}

    def analyze_full(self, raw_image_bytes):
        image_numpy = self._decode_bytes_to_numpy(raw_image_bytes)
        if image_numpy is None: return {"error": "Archivo corrupto o no es imagen"}
        return {"telemetry_roi": self._process_roboflow_hybrid(image_numpy)}