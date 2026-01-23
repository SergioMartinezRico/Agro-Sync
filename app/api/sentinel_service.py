import os
import io
import base64
import numpy as np
import matplotlib
# Configurar backend no interactivo para servidor web
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import shapely.wkt
import shapely.geometry
from datetime import datetime as dt, timedelta

# Importaciones de Sentinel Hub
from sentinelhub import (
    SHConfig, SentinelHubRequest, SentinelHubCatalog,
    DataCollection, MimeType, CRS, Geometry, bbox_to_dimensions
)

# Constantes de configuración (Indices y Script)
INDICES_CONFIG = [
    {"name": "NDVI", "colormap": "RdYlGn", "vmin": 0.0, "vmax": 1.0, "labels": ["Suelo", "Bajo", "Medio", "Alto", "Muy Alto"]},
    {"name": "NDWI", "colormap": "RdYlBu", "vmin": -1.0, "vmax": 1.0, "labels": ["Muy Seco", "Seco", "Neutro", "Húmedo", "Agua"]},
    {"name": "NDRE", "colormap": "RdYlGn", "vmin": 0.0, "vmax": 0.8, "labels": ["Bajo", "Medio-Bajo", "Medio", "Alto", "Muy Alto"]},
    {"name": "GNDVI", "colormap": "RdYlGn", "vmin": 0.0, "vmax": 1.0, "labels": ["Bajo", "Medio-Bajo", "Medio", "Alto", "Muy Alto"]}
]

EVALSCRIPT = """
// VERSION=3
function setup() {
  return {
    input: ["B03", "B04", "B05", "B08", "dataMask"],
    output: { bands: 4, sampleType: "FLOAT32" }
  };
}

function evaluatePixel(sample) {
  if (sample.dataMask == 0) return [NaN, NaN, NaN, NaN];
  let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
  let ndwi = (sample.B03 - sample.B08) / (sample.B03 + sample.B08);
  let ndre = (sample.B08 - sample.B05) / (sample.B08 + sample.B05);
  let gndvi = (sample.B08 - sample.B03) / (sample.B08 + sample.B03);
  return [ndvi, ndwi, ndre, gndvi];
}
"""

class SentinelService:
    def __init__(self):
        """Inicializa la configuración de Sentinel Hub desde variables de entorno."""
        self.config = SHConfig()
        self.config.sh_client_id = os.environ.get("SH_CLIENT_ID")
        self.config.sh_client_secret = os.environ.get("SH_CLIENT_SECRET")
        
        if not self.config.sh_client_id or not self.config.sh_client_secret:
            raise ValueError("Credenciales de Sentinel Hub no encontradas en variables de entorno.")

    def _generar_leyenda(self, config_idx):
        """Helper privado para generar la estructura de la leyenda."""
        cmap = plt.get_cmap(config_idx["colormap"])
        labels = config_idx["labels"]
        steps = len(labels)
        legend_items = []
        
        for i in range(steps):
            val_norm = i / (steps - 1)
            rgba = cmap(val_norm)
            val_real = config_idx["vmin"] + (val_norm * (config_idx["vmax"] - config_idx["vmin"]))
            legend_items.append({
                "value": round(val_real, 2),
                "color": mcolors.to_hex(rgba),
                "label": labels[i]
            })
        return {
            "title": f"Índice {config_idx['name']}",
            "min": config_idx["vmin"],
            "max": config_idx["vmax"],
            "palette": legend_items
        }

    def _aplicar_colormap_base64(self, matriz, config_idx):
        """Helper privado para convertir matriz numpy a imagen Base64."""
        norm = mcolors.Normalize(vmin=config_idx["vmin"], vmax=config_idx["vmax"])
        cmap = plt.get_cmap(config_idx["colormap"])
        mapped_img = cmap(norm(matriz))
        
        # Transparencia para NaN
        mask = np.isnan(matriz)
        mapped_img[mask] = [0, 0, 0, 0]

        buffer = io.BytesIO()
        plt.imsave(buffer, mapped_img, format='png')
        buffer.seek(0)
        b64_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
        buffer.close()
        return b64_str

    def _wkt_to_geojson(self, wkt_str):
        g = shapely.wkt.loads(wkt_str)
        return shapely.geometry.mapping(g)

    def analyze_polygon(self, wkt_polygon):
        """
        Método principal.
        Recibe un WKT (string), descarga datos de Sentinel y retorna estructura JSON.
        """
        # 1. Geometría y BBox
        geometry_wgs84 = Geometry(geometry=wkt_polygon, crs=CRS.WGS84)
        bbox = geometry_wgs84.bbox

        # 2. Resolución dinámica
        lon_center = (bbox.min_x + bbox.max_x) / 2
        lat_center = (bbox.min_y + bbox.max_y) / 2
        utm_zone = int((lon_center + 180) / 6) + 1
        epsg = 32600 + utm_zone if lat_center >= 0 else 32700 + utm_zone
        
        geometry_utm = geometry_wgs84.transform(CRS(str(epsg)))
        width_px, height_px = bbox_to_dimensions(geometry_utm.bbox, resolution=10)

        # 3. Búsqueda de imágenes (últimos 30 días, baja nubosidad)
        catalog = SentinelHubCatalog(config=self.config)
        hoy = dt.utcnow()
        hace_30_dias = hoy - timedelta(days=30)

        resultados = list(catalog.search(
            collection=DataCollection.SENTINEL2_L2A,
            geometry=geometry_wgs84,
            time=(hace_30_dias, hoy),
            filter="eo:cloud_cover < 20"
        ))

        if not resultados:
            return None # O lanzar una excepción personalizada si prefieres

        # Tomar la más reciente
        resultados.sort(key=lambda x: x["properties"]["datetime"], reverse=True)
        fecha_img = resultados[0]["properties"]["datetime"].split("T")[0]

        # 4. Request
        request = SentinelHubRequest(
            evalscript=EVALSCRIPT,
            input_data=[SentinelHubRequest.input_data(
                data_collection=DataCollection.SENTINEL2_L2A,
                time_interval=(fecha_img, fecha_img),
                mosaicking_order="leastCC"
            )],
            responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
            geometry=geometry_wgs84,
            size=(width_px, height_px),
            config=self.config
        )
        
        data = request.get_data()
        if not data:
            return None

        raw_cube = data[-1] 
        layers = []
        
        for i, config_idx in enumerate(INDICES_CONFIG):
            band_matrix = raw_cube[:, :, i]
            img_b64 = self._aplicar_colormap_base64(band_matrix, config_idx)
            legend_obj = self._generar_leyenda(config_idx)
            
            layers.append({
                "type": config_idx["name"],
                "image_data": f"data:image/png;base64,{img_b64}",
                "legend": legend_obj
            })

        return {
            "date": fecha_img,
            "geometry": self._wkt_to_geojson(wkt_polygon),
            "image_bounds": [[bbox.min_y, bbox.min_x], [bbox.max_y, bbox.max_x]],
            "layers": layers
        }