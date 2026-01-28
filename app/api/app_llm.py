from flask import Blueprint, request, jsonify
import os
from groq import Groq
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from models.convers import get_messages_by_conversation  # ← Reutilizamos
from app.core.database import get_db_connection
from psycopg2.extras import RealDictCursor

messages_bp = Blueprint('messages', __name__, url_prefix='/agrosync-api/chat')

llm = ChatGroq(
    model="llama-3.3-70b-versatile", 
    temperature=0.3,
    groq_api_key=os.getenv("GROQ_API_KEY")
)

prompt = ChatPromptTemplate.from_messages([
    ("system", """Eres un especialista en agricultura.

                        Flujo de conversación obligatorio:

                        1. Si el usuario aún no ha hecho ninguna pregunta técnica,
                        responde únicamente con:
                        "Hola, ¿en qué puedo ayudarte?"
                        y no añadas ninguna otra información.

                        2. Cuando el usuario haga una pregunta técnica, responde según el rol:

                        - Rol "director":
                        Respuesta ejecutiva, conclusiones y decisiones clave.

                        - Rol "asesor":
                        Lenguaje formal, hipótesis, referencias técnicas y estrategias.

                        - Rol "productor":
                        Lenguaje práctico, recomendaciones directas y manejo en campo.

                        - Rol "analista":
                        Lenguaje técnico, métricas, umbrales y modelos de decisión.

                        Reglas de estilo:
                        - No te presentes.
                        - No expliques tu rol.
                        - No saludes después del primer mensaje.
                        - Responde de forma directa y concisa (máx. 6 líneas).
- Contexto anterior: {history}
- Usuario: {username} | Rol: {rol}"""),
    MessagesPlaceholder(variable_name="history", optional=True),  # ← ¡ACTIVADO!
    ("human", "{input}"),
])



chain = prompt | llm

@messages_bp.route('/conversations/<int:conversation_id>/messages', methods=['POST'])
def add_message(conversation_id):
    print("🚀 POST messages")
    try:
        data = request.get_json()
        firebase_uid_user = data.get('firebase_uid_user')
        content = data.get('content')
        rol = data.get('rol', 'productor')
        
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1️⃣ CARGAR HISTORIAL (últimos 10 mensajes)
                print("📚 Cargando historial...")
                cur.execute("""
                    SELECT rol as role, contenido as content 
                    FROM mensaje 
                    WHERE conversacion_id = %s 
                    ORDER BY created_at DESC 
                    LIMIT 10
                """, (conversation_id,))
                history_raw = cur.fetchall()
                
                # Convertir a formato LangChain Messages
                history = []
                for msg in reversed(history_raw):  # Revertir para orden cronológico
                    if msg['role'] == 'user':
                        history.append(("human", msg['content']))
                    elif msg['role'] == 'assistant':
                        history.append(("ai", msg['content']))
                
                print(f"📚 Historial cargado: {len(history)} mensajes")

                # 2️⃣ GUARDAR USUARIO
                cur.execute("""
                    INSERT INTO mensaje (conversacion_id, rol, contenido)
                    VALUES (%s, %s, %s) RETURNING id::text as id, rol as role, contenido as content, created_at as timestamp
                """, (conversation_id, 'user', content))
                user_message = cur.fetchone()

                # 3️⃣ LLM CON HISTORIAL REAL
                print("🤖 LLM con contexto...")
                response = chain.invoke({
                    "input": content,
                    "rol": rol, 
                    "username": firebase_uid_user,
                    "history": history  # ← ¡MEMORIA ACTIVADA!
                })
                response_text = response.content

                # 4️⃣ ASSISTANT
                cur.execute("""
                    INSERT INTO mensaje (conversacion_id, rol, contenido)
                    VALUES (%s, %s, %s) RETURNING id::text as id, rol as role, contenido as content, created_at as timestamp
                """, (conversation_id, 'assistant', response_text))
                assistant_message = cur.fetchone()
                
                conn.commit()

                # 5️⃣ DEVOLVER NUEVOS
                new_messages = [user_message, assistant_message]
                print(f"🚀 {len(new_messages)} nuevos msgs + {len(history)} contexto")
                return jsonify(new_messages), 201

        finally:
            conn.close()

    except Exception as e:
        print(f"💥 ERROR: {e}")
        return jsonify({"error": str(e)}), 500
