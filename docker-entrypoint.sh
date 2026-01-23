#!/bin/bash
set -e

mkdir -p /app/logs

echo "🚀 Iniciando AgroSync + MeteoTask + AlertasTask..."

# 1. Inicia meteoTask.py EN SEGUNDO PLANO
echo "🌦️  Iniciando MeteoTask..."
python -u /app/app/ProgramedJobs/meteoTask.py &
METEO_PID=$!
echo $METEO_PID > /tmp/meteo.pid

# 2. Inicia alertasTask.py EN SEGUNDO PLANO
echo "🚨 Iniciando AlertasTask..."
python -u /app/app/ProgramedJobs/alertasTask.py &
ALERTAS_PID=$!
echo $ALERTAS_PID > /tmp/alertas.pid

# 3. Espera que ambos arranquen
sleep 5

echo "✅ MeteoTask PID: $METEO_PID"
echo "✅ AlertasTask PID: $ALERTAS_PID"
echo "🌤️ MeteoTask + AlertasTask corriendo en background"
echo "🔥 Iniciando Flask en puerto 8282..."

# 4. Flask en PRIMER PLANO
exec python -u app/main.py
