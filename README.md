# AgroSync Backend & Data Engine 🚜🛰️

**AgroSync** es una plataforma avanzada de agricultura de precisión que integra **Ingeniería de Datos Espaciales**, **Inteligencia Artificial (LLMs)** y **Modelado Agronómico** en tiempo real.

Este repositorio contiene el backend completo: una API RESTful de alto rendimiento que orquesta la ingesta de imágenes satelitales (Sentinel-2, GEE), procesa datos meteorológicos hiperlocales y ejecuta un motor de alertas preventivas (heladas, sequías, plagas) mediante pipelines ETL automatizados y contenerizados.

## 🛠️ Mi Contribución: Core de Inteligencia e Infraestructura
Como responsable del área de **Data Engineering e IA**, desarrollé y desplegué los tres motores críticos que dotan de inteligencia a la plataforma. He segregado estos componentes en microservicios independientes para optimizar recursos y escalabilidad:

[![GitHub Repo](https://img.shields.io/badge/AgroDetect_API-Salud_Vegetal-2ea44f?style=for-the-badge&logo=github)](https://github.com/SergioMartinezRico/api_plant_detect)
* **Rol:** Engine de salud vegetal basado en el middleware **PlantBioEngine**.
* **Hito Técnico:** Procesamiento de imágenes (Base64/URL) con análisis taxonómico y protocolos de tratamiento automatizados.
* **Stack:** Flask, Python, REST API.

[![GitHub Repo](https://img.shields.io/badge/AgroEngine-Vision_360_&_Satelital-007acc?style=for-the-badge&logo=github)](https://github.com/SergioMartinezRico/agro_engine)
* **Rol:** Motor de visión que convierte detecciones visuales en **vectores cartesianos (x, y, z)**.
* **Hito Técnico:** Algoritmo de proyección para localizar anomalías en entornos 360° mediante modelos contenerizados en **Docker**.
* **Stack:** OpenCV, Hugging Face, PyTorch.

### 🛰️ Data Engine & Sentinel-2 Pipeline
* **Rol:** Orquestación de pipelines ETL para ingesta satelital dinámica.
* **Hito Técnico:** Generación *on-demand* de mapas de calor multiespectrales (**NDVI, NDWI, SAVI**) integrando la API de **Sentinel Hub**.

## 🏗️ Arquitectura del Sistema

El sistema utiliza una arquitectura de **Contenedor Híbrido Monolítico**. Un único servicio Docker orquesta tanto la capa de presentación (API Flask) como los procesos de fondo (Workers), optimizando recursos y despliegue.

### Componentes Principales

1.  **API REST (Flask & Blueprints):**
    * Gestión de fincas y lotes sincronizada con **Auravant**.
    * Generación de índices espectrales (NDVI, NDWI, GNDVI) *on-demand* vía **Sentinel Hub**.
    * Chatbot agronómico potenciado por IA (LangChain + Groq).

2.  **Data Engine (ProgramedJobs):**
    * **Orquestación:** Scripts Python ejecutados como demonios (*daemons*), programados con `schedule`.
    * **Google Earth Engine (GEE):** Pipeline "Headless" (Service Account) para descarga masiva de históricos de vegetación.
    * **Open-Meteo:** Ingesta de datos climáticos (forecast e históricos) con resolución horaria.

3.  **Motor de Alertas (Risk Modeling):**
    * Algoritmos propios basados en ventanas deslizantes (*rolling windows*) de Pandas.
    * Cálculo de **SPI (Standardized Precipitation Index)** para detección científica de sequía.
    * **Fusión de Datos:** Cruce de anomalías climáticas + estrés hídrico del suelo para calcular probabilidad y severidad de riesgos (Heladas, Inundaciones, Plagas).
  
    ## 🛠 Tech Stack

* **Lenguaje:** Python 3.11 (Slim Image)
* **Web Framework:** Flask 3.0 (Blueprints modularizados)
* **Data Science:** Pandas 2.3, NumPy, Shapely (Procesamiento Geoespacial)
* **Geospatial APIs:**
    * `earthengine-api` (Google Earth Engine)
    * `sentinelhub` (Sentinel-2 L2A)
* **AI & LLM:** LangChain, Groq (Asistente conversacional inteligente).
* **Infraestructura:** Docker, Docker Compose, Schedule.
* **Base de Datos:** PostgreSQL (Driver `psycopg2` para alto rendimiento).

* ## ⚙️ Pipelines Automatizados (Background Tasks)

El contenedor inicializa automáticamente los siguientes procesos paralelos al arrancar (definidos en `docker-entrypoint.sh`):

| Proceso | Horario (UTC) | Descripción |
| :--- | :--- | :--- |
| **histVegetaTask** | 03:00 AM | Conecta con GEE, descarga índices de vegetación de los últimos días y realiza UPSERTs en la BD. |
| **histMeteoTask** | 04:00 AM | Descarga históricos climáticos de Open-Meteo para el entrenamiento de modelos de predicción. |
| **alertasTask** | 05:00 AM | **Core del negocio.** Analiza ventanas de 3, 7 y 30 días para calcular riesgos de Helada, Inundación y Sequía (SPI + Suelo). |
| **meteoTask** | Cada 60 min | Actualiza el pronóstico meteorológico en tiempo real (Current Weather). |
| **Flask API** | *Daemon* | Servidor web escuchando en el puerto 8282 para peticiones del frontend. |

## 🔐 Configuración (.env)

El proyecto requiere un archivo `.env` en la raíz con las siguientes credenciales para funcionar:


# --- Configuración General ---
PLANT_ID_KEY=tu_clave_publica
PYTHONPATH=/app

# --- Base de Datos (PostgreSQL) ---
DATABASE_URL=postgresql://user:pass@host:5432/db_name
DB_HOST=localhost
DB_NAME=agrosync_db
DB_USER=postgres
DB_PASSWORD=secret
DB_PORT=5432

# --- Integraciones Externas ---
# Auravant
AURAVANT_AUTH_URL=[https://livingcarbontech.auravant.com/api/](https://livingcarbontech.auravant.com/api/)
AURAVANT_BASE_URL=[https://api.auravant.com/api/](https://api.auravant.com/api/)
AURAVANT_AUTH_USER=usuario
AURAVANT_AUTH_PASS=password
SUBDOMAIN=...
EXTENSION_ID=...
SECRET=...

# Sentinel Hub
SH_CLIENT_ID=client_id
SH_CLIENT_SECRET=client_secret

# Google Earth Engine
GOOGLE_CLOUD_PROJECT=desafio-tripulaciones-xxxxx

---

### Capítulo 6: Instalación y Despliegue (Docker)
*Instrucciones basadas en tu `Dockerfile` y `docker-compose.yml`.*


## 🚀 Despliegue con Docker

### Prerrequisitos
1.  Tener Docker y Docker Compose instalados.
2.  Colocar el archivo JSON de credenciales de Google en la carpeta `creds/`.

### Opción A: Ejecución Directa


# 1. Construir la imagen
docker build -t agrosync-api .

# 2. Ejecutar contenedor (Puerto 8282)
# Nota: Montamos el volumen de credenciales como read-only
docker run -d \
  --name agrosync-api \
  -p 8282:8282 \
  -v $(pwd)/creds:/app/app/creds:ro \
  --env-file .env \
  agrosync-api

  ## 🗄️ Estructura de Base de Datos

El sistema espera las siguientes tablas principales en PostgreSQL:

* `usuarios`: Autenticación y datos de perfil (SHA256).
* `parcels`: Catastro de fincas con geometrías (`uid_parcel`, `coordinates`).
* `weather_archive`: Histórico climático diario/horario.
* `parcel_vegetation_indices`: Histórico de NDVI, GNDVI, NDWI, SAVI.
* `alertas`: Registro diario de riesgos calculados (Helada, Sequía, etc.).
* `conversacion` / `mensaje`: Historial del Chatbot IA.

  ## 📡 API Endpoints Reference

### 🌱 Campos (`/agrosync-api`)
* `POST /getfields`: Sincronizar campos.
* `POST /agregarlote`: Crear geometría poligonal.

### 🛰️ Mapas e Inteligencia (`/agrosync-api`)
* `POST /maps_sentinel`: Obtener capas procesadas (NDVI, RGB) en Base64.
* `POST /forecast_nextweek`: Pronóstico extendido + Alertas de Riesgo.

### 💬 Chat IA (`/agrosync-api/chat`)
* `POST /new_conversation`: Iniciar hilo con el asistente.
* `GET /conversations/{id}/messages`: Recuperar contexto.

## 📂 Estructura del Proyecto

```text
/app
├── api/                 # Endpoints Flask (Blueprints)
├── core/                # Configuración y Conexión DB (Singleton)
├── models/              # Consultas SQL "Bare Metal" (Psycopg2)
├── ProgramedJobs/       # Workers ETL y Lógica de Negocio
│   ├── alertasTask.py   # Algoritmos de riesgo y UPSERTs
│   ├── histVegetaTask.py# Integración GEE
│   └── ...
├── creds/               # Credenciales (Service Accounts)
├── docker-entrypoint.sh # Script de arranque híbrido
├── Dockerfile           # Imagen Python 3.11 Slim
└── main.py              # Punto de entrada de la aplicación

```

## 👥 Equipo de Desarrollo

Este proyecto es el resultado del trabajo colaborativo en **The Bridge**:

* **Data Science & AI Engine:**
  * [![LinkedIn](https://img.shields.io/badge/LinkedIn-Sergio_Martinez_Rico-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/sergio-martinez-rico-)
  * [![LinkedIn](https://img.shields.io/badge/LinkedIn-Rebeca_Pérez-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/rebeca-perez-castanos/)
  * [![LinkedIn](https://img.shields.io/badge/LinkedIn-Itxaso_Campos-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/itxasocampos/)
  * [![LinkedIn](https://img.shields.io/badge/LinkedIn-Mikel_Lizarraga-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/mikel-lizarraga/)
  * [![LinkedIn](https://img.shields.io/badge/LinkedIn-Miguel_Mateo-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/miguelmateod/)
  * [![LinkedIn](https://img.shields.io/badge/LinkedIn-Noha_Hussien-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/noha-hussien-9b940b168/)
  * [![LinkedIn](https://img.shields.io/badge/LinkedIn-Matilde_Valeruz-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/matildevaleruz/?locale=es)
