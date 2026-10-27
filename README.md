# Chatbot con Gemini + FastMCP + Pusher

Chatbot de atención al cliente con cuatro piezas:

| Pieza | Archivo | Rol |
|---|---|---|
| Frontend | `frontend/` (HTML, CSS, JS) | Interfaz de chat |
| Backend | `backend/app.py` (FastAPI) | API REST, historial por sesión, cliente FastMCP y ciclo de function calling con Gemini |
| Servidor MCP | `backend/mcp_server.py` (FastMCP) | 4 tools: `saludo`, `horario_atencion`, `medios_de_pago`, `informacion_empresa` |
| Tiempo real | Pusher (canal privado por sesión) | Entrega la respuesta del bot al navegador |
| Modelo | Gemini (SDK `google-genai`) | Decide cuándo llamar una tool y redacta la respuesta |

## Flujo

```
Navegador --POST /api/chat--> FastAPI (responde 202) --> Gemini --(function call)--> FastMCP Client
    ^                                  |                                                  |
    |                                  +<----------------- resultado de la tool ----------+
    +------ evento "bot-message" ------ Pusher (canal private-chat-<session_id>) <-- FastAPI
```

- El backend lista las tools del servidor con `fastmcp.Client`, las declara a Gemini y, cuando Gemini pide una, la ejecuta con `call_tool`.
- El navegador se suscribe al canal privado `private-chat-<session_id>`; `POST /api/pusher/auth` autoriza la suscripción.
- Eventos: `bot-message` (`reply`, `tools_used`) y `bot-error` (`detail`).
- `PUSHER_SECRET` vive solo en el backend. Al frontend solo llegan `key` y `cluster` (`GET /api/config`).

El backend arranca `mcp_server.py` como subproceso (stdio) y le pasa la sesión MCP a Gemini
como herramienta; el SDK ejecuta las llamadas de forma automática.

## Instalación

Requiere Python 3.10 o superior.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # Windows: copy .env.example .env
# edita .env: GEMINI_API_KEY y las 4 variables PUSHER_*
```

## Ejecutar

```bash
cd backend
python app.py
```

Abre http://127.0.0.1:8000

## Personalizar

- Datos de la empresa, horario y medios de pago: `backend/mcp_server.py` (diccionarios al inicio).
- Tono y reglas del asistente: `SYSTEM_PROMPT` en `backend/app.py`.
- Modelo: variable `GEMINI_MODEL` en `.env`.
- Agregar una tool: define otra función con `@mcp.tool` en `mcp_server.py`; el backend la detecta al iniciar y se la declara a Gemini.

## Probar el servidor MCP por separado

```bash
fastmcp dev backend/mcp_server.py
```
