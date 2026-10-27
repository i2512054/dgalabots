"""
Backend del chatbot.

- Se conecta con FastMCP (Client) al servidor MCP mcp_server.py, que arranca como subproceso (stdio).
- Convierte las tools MCP en function declarations de Gemini y ejecuta el ciclo de
  function calling: Gemini pide una tool -> el backend la llama en el MCP -> devuelve el resultado.
- POST /api/chat responde 202 de inmediato y procesa en segundo plano.
- La respuesta del bot se entrega al navegador por Pusher (canal privado por sesión).

Ejecutar:  python app.py
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs
from flask import Flask

import pusher
import uvicorn
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastmcp import Client
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

load_dotenv(BASE_DIR / ".env")

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MAX_TURNOS_HISTORIAL = 20  # mensajes (usuario + asistente) que se conservan por sesión
MAX_RONDAS_TOOLS = 5       # límite de idas y vueltas con tools por mensaje
PREFIJO_CANAL = "private-chat-"

SYSTEM_PROMPT = """
Eres un asistente de la Joyería D'Gala.
Responde solo preguntas relacionadas con la Joyería D'Gala. Cuando no sepas una respuesta, solicitala que se contacten al correo joyasoyeriaDGala@hotmail.com o que nos llamen al celular 916520052.
Genera respuestas cortas que no sobrepasen las 250 palabras sin explicaciones largas.
Responde siempre en español, con tono amable, claro y breve.

Tienes herramientas para consultar datos reales de la empresa:
- saludo: cuando el usuario salude o inicie la conversación.
- horario_atencion: horarios, días de atención y si estamos abiertos ahora.
- medios_de_pago: formas de pago aceptadas.
- informacion_empresa: qué es la empresa, dirección y contacto.
- reserva_de_citas: enlace para obtener un link para reservar citas.
- lista_de_facturas: cuando el usuario solicita las compras realizadas.
- lista_de_categorias: cuando el usuario solicita la lista de categorias.
- lista_de_productos_por_categoria: cuando el usuario solicita la lista de productos por categoria.

Reglas:
- Usa las herramientas para responder estos temas; no inventes datos.
- Si preguntan algo fuera de estos temas, explica con amabilidad que solo puedes
  ayudar con saludos, horario, medios de pago e información de la empresa.
- No uses tablas. Para listas usa viñetas simples con guion.
"""

# Estado compartido (se crea al iniciar la aplicación)
estado: dict = {}


def _variable_obligatoria(nombre: str) -> str:
    valor = os.getenv(nombre)
    if not valor:
        raise RuntimeError(f"Falta {nombre}. Revisa tu archivo .env (ver .env.example).")
    return valor


def _a_tool_gemini(tools_mcp) -> types.Tool:
    """Convierte las tools del servidor MCP en function declarations de Gemini."""
    declaraciones = []
    for tool in tools_mcp:
        esquema = tool.input_schema or {}# esquema = tool.inputSchema or {}
        declaraciones.append(
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description or "",
                # Las tools sin parámetros se declaran sin esquema.
                parameters_json_schema=esquema if esquema.get("properties") else None,
            )
        )
    return types.Tool(function_declarations=declaraciones)


@asynccontextmanager
async def lifespan(app: FastAPI):
    api_key = _variable_obligatoria("GEMINI_API_KEY")

    estado["pusher_key"] = _variable_obligatoria("PUSHER_KEY")
    estado["pusher_cluster"] = _variable_obligatoria("PUSHER_CLUSTER")
    estado["pusher"] = pusher.Pusher(
        app_id=_variable_obligatoria("PUSHER_APP_ID"),
        key=estado["pusher_key"],
        secret=_variable_obligatoria("PUSHER_SECRET"),
        cluster=estado["pusher_cluster"],
        ssl=True,
    )

    # FastMCP detecta un archivo .py y lo ejecuta como subproceso por stdio.
    async with Client(str(BASE_DIR / "mcp_server.py")) as mcp_client:
        tools = await mcp_client.list_tools()
        print("Tools MCP disponibles:", [t.name for t in tools])

        estado["mcp_client"] = mcp_client
        estado["gemini_tools"] = _a_tool_gemini(tools)
        estado["client"] = genai.Client(api_key=api_key)
        estado["historiales"] = {}  # session_id -> lista de types.Content
        yield

    estado.clear()


app = FastAPI(title="Chatbot Gemini + FastMCP + Pusher", lifespan=lifespan)

# CORS abierto a cualquier origen, metodo y cabecera (equivalente a "*.*").
# Nota: con allow_origins=["*"] el navegador no permite credenciales
# (cookies / Authorization), por eso allow_credentials queda en False.
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "*",
    "Access-Control-Allow-Headers": "*",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_\-]+$")
    message: str = Field(..., min_length=1, max_length=2000)


class ResetRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_\-]+$")


async def ejecutar_tool(nombre: str, argumentos: dict) -> str:
    """Llama una tool en el servidor MCP (vía FastMCP Client) y devuelve su texto."""
    try:
        resultado = await estado["mcp_client"].call_tool(nombre, argumentos)
    except Exception as exc:  # noqa: BLE001
        print(f"Error en la tool {nombre}:", repr(exc), file=sys.stderr)
        return f"Error al ejecutar la herramienta {nombre}."

    textos = [bloque.text for bloque in resultado.content if hasattr(bloque, "text")]
    return "\n".join(textos) if textos else "La herramienta no devolvió contenido."


async def generar_respuesta(historial: list[types.Content], texto: str) -> tuple[str, list[str]]:
    """Ciclo de function calling con Gemini. Devuelve (respuesta, tools_usadas)."""
    mensaje_usuario = types.Content(role="user", parts=[types.Part(text=texto)])
    contenidos = historial + [mensaje_usuario]
    tools_usadas: list[str] = []

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.3,
        tools=[estado["gemini_tools"]],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    for _ in range(MAX_RONDAS_TOOLS):
        response = await estado["client"].aio.models.generate_content(
            model=MODEL, contents=contenidos, config=config
        )
        llamadas = response.function_calls or []

        if not llamadas:
            respuesta = (response.text or "").strip() or (
                "No pude generar una respuesta. ¿Puedes reformular tu pregunta?"
            )
            # Guardamos solo el texto de cada turno para mantener el historial liviano.
            historial.append(mensaje_usuario)
            historial.append(types.Content(role="model", parts=[types.Part(text=respuesta)]))
            del historial[:-MAX_TURNOS_HISTORIAL]
            return respuesta, tools_usadas

        # Se conserva el turno del modelo tal cual (incluye la llamada a la tool).
        contenidos.append(response.candidates[0].content)

        partes_respuesta = []
        for llamada in llamadas:
            if llamada.name not in tools_usadas:
                tools_usadas.append(llamada.name)
            resultado = await ejecutar_tool(llamada.name, dict(llamada.args or {}))
            partes_respuesta.append(
                types.Part.from_function_response(
                    name=llamada.name, response={"result": resultado}
                )
            )
        contenidos.append(types.Content(role="user", parts=partes_respuesta))

    raise RuntimeError("Gemini superó el máximo de rondas de herramientas.")


async def publicar(session_id: str, evento: str, datos: dict) -> None:
    """Envía un evento al canal privado de la sesión (la librería de Pusher es síncrona)."""
    canal = f"{PREFIJO_CANAL}{session_id}"
    try:
        await asyncio.to_thread(estado["pusher"].trigger, canal, evento, datos)
    except Exception as exc:  # noqa: BLE001
        print("Error publicando en Pusher:", repr(exc), file=sys.stderr)


async def procesar_mensaje(session_id: str, texto: str) -> None:
    """Consulta a Gemini (con las tools MCP) y publica la respuesta por Pusher."""
    historial = estado["historiales"].setdefault(session_id, [])
    try:
        respuesta, tools_usadas = await generar_respuesta(historial, texto)
    except Exception as exc:  # noqa: BLE001
        print("Error generando la respuesta:", repr(exc), file=sys.stderr)
        await publicar(
            session_id,
            "bot-error",
            {"detail": "No pude comunicarme con Gemini. Intenta de nuevo en unos segundos."},
        )
        return

    await publicar(session_id, "bot-message", {"reply": respuesta, "tools_used": tools_usadas})


@app.post("/api/chat", status_code=202)
async def chat(req: ChatRequest, background: BackgroundTasks):
    background.add_task(procesar_mensaje, req.session_id, req.message)
    return {"status": "processing"}


@app.post("/api/pusher/auth")
async def pusher_auth(request: Request):
    """Autoriza la suscripción a canales privados (Pusher envía socket_id y channel_name)."""
    cuerpo = parse_qs((await request.body()).decode())
    socket_id = cuerpo.get("socket_id", [""])[0]
    canal = cuerpo.get("channel_name", [""])[0]

    if not socket_id or not canal.startswith(PREFIJO_CANAL):
        raise HTTPException(status_code=403, detail="Canal no permitido")

    return estado["pusher"].authenticate(channel=canal, socket_id=socket_id)


@app.get("/api/config")
async def config():
    """Datos públicos que necesita el frontend (el secret nunca sale del backend)."""
    return {"pusher_key": estado["pusher_key"], "pusher_cluster": estado["pusher_cluster"]}


@app.post("/api/reset")
async def reset(req: ResetRequest):
    estado["historiales"].pop(req.session_id, None)
    return {"ok": True}


@app.get("/api/health")
async def health():
    return {"status": "ok", "model": MODEL}


# El frontend se monta al final para que no tape las rutas /api/*
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    # Sin --reload a propósito: en Windows el modo reload puede romper los subprocesos del MCP.
    uvicorn.run(
        app, host="0.0.0.0"
    )
#    uvicorn.run(
#        app, host="0.0.0.0", 
#        port=int(os.getenv("PORT", "8001")), 
#        ssl_keyfile="key.pem", 
#        ssl_certfile="cert.pem",
#    )
