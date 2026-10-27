//const log = document.getElementById("log");
const log = document.getElementById("messagesContainer");
const form = document.getElementById("composer");
//const form = document.getElementById("frm");
const input = document.getElementById("input");
const input2 = document.getElementById("messageInput");
const sendBtn = document.getElementById("send");
const sendBtn2 = document.getElementById("sendBtn");
const resetBtn = document.getElementById("reset");
const chips = document.querySelectorAll(".chip");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");

const MENSAJE_BIENVENIDA =
  "¡Hola!, Soy el asistente virtual de la Joyería D'Gala.. Puedo contarte sobre nuestro horario de atención, " +
  "los medios de pago y la información de la empresa. ¿En qué te ayudo?";

const NOMBRES_TOOLS = {
  saludo: "Saludo",
  horario_atencion: "Horario de atención",
  medios_de_pago: "Medios de pago",
  informacion_empresa: "Información de la empresa",
  reserva_de_citas: "Reserva de citas",
  lista_de_facturas: "Lista de facturas",
  lista_de_categorias: "Lista de categorías",
  lista_de_productos_por_categoria: "Lista de productos por categoría"
};

let sessionId = localStorage.getItem("session_id");
if (!sessionId) {
  sessionId = crypto.randomUUID();
  localStorage.setItem("session_id", sessionId);
}

let enviando = false;
let escribiendoEl = null;
let temporizador = null;
const TIEMPO_MAXIMO_MS = 60000;

/* ---------- Pusher ---------- */
function mostrarEstado(conectado, texto) {
  statusDot.classList.toggle("off", !conectado);
  statusText.textContent = texto;
}

function terminarEspera() {
  clearTimeout(temporizador);
  if (escribiendoEl) { escribiendoEl.remove(); escribiendoEl = null; }
  bloquear(false);
  input.focus();
}

function alRecibirMensaje(data) {
  terminarEspera();
  agregarMensaje("bot", data.reply, { tools: data.tools_used || [] });
}

function alRecibirError(data) {
  terminarEspera();
  agregarMensaje("bot", data.detail || "Ocurrió un error. Intenta de nuevo.", { error: true });
}

async function iniciarPusher() {
  const res = await fetch("/api/config");
  if (!res.ok) throw new Error("No se pudo leer la configuración del servidor.");
  const cfg = await res.json();

  const pusher = new Pusher(cfg.pusher_key, {
    cluster: cfg.pusher_cluster,
    channelAuthorization: { endpoint: "/api/pusher/auth" },
  });

  pusher.connection.bind("state_change", ({ current }) => {
    if (current === "connected") mostrarEstado(true, "Asistente virtual en línea");
    else if (current === "connecting" || current === "unavailable") mostrarEstado(false, "Reconectando…");
    else if (current === "failed" || current === "disconnected") mostrarEstado(false, "Sin conexión");
  });

  const canal = pusher.subscribe(`private-chat-${sessionId}`);
  canal.bind("bot-message", alRecibirMensaje);
  canal.bind("bot-error", alRecibirError);

  await new Promise((resolve, reject) => {
    canal.bind("pusher:subscription_succeeded", resolve);
    canal.bind("pusher:subscription_error", () =>
      reject(new Error("No se pudo autorizar el canal de mensajes.")));
  });
}

// Promesa que se resuelve cuando el canal está listo para recibir respuestas.
const canalListo = iniciarPusher().catch((err) => {
  mostrarEstado(false, "Sin conexión");
  throw err;
});
canalListo.catch(() => {}); // evita el aviso de "unhandled rejection"; el error se muestra al enviar

/* ---------- Render ---------- */
function escapeHtml(texto) {
  return texto
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Convierte el texto del bot a HTML seguro: negritas, viñetas y párrafos.
function formatear(texto) {
  const lineas = escapeHtml(texto).split("\n");
  let html = "";
  let enLista = false;

  for (const linea of lineas) {
    const item = linea.match(/^\s*[-*•]\s+(.*)$/);
    const conNegrita = (s) => s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

    if (item) {
      if (!enLista) { html += "<ul>"; enLista = true; }
      html += `<li>${conNegrita(item[1])}</li>`;
    } else {
      if (enLista) { html += "</ul>"; enLista = false; }
      if (linea.trim()) html += `<p>${conNegrita(linea)}</p>`;
    }
  }
  if (enLista) html += "</ul>";
  return html;
}

function agregarMensaje(rol, texto, { tools = [], error = false } = {}) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${rol}${error ? " error" : ""}`;

  const burbuja = document.createElement("div");
  burbuja.className = "bubble";
  if (rol === "bot") burbuja.innerHTML = formatear(texto);
  else burbuja.innerHTML = texto;
  wrap.appendChild(burbuja);

  const fila = document.createElement("div");
  fila.className = "tools";
  const badge = document.createElement("span");
  badge.className = "tool-badge";    
  badge.innerHTML = "<b>" + getTimeResponse() + "</b>";
  fila.appendChild(badge);
  wrap.appendChild(fila);

  if (tools.length) {
    console.clear();
    console.log(tools);
    for (const t of tools) {
      let x = `Consultó: ${NOMBRES_TOOLS[t] || t}`;
      console.log(x);
      console.log("-------------------------");
      console.log(texto);
    }
  }

  /*if (tools.length) {
    const fila = document.createElement("div");
    fila.className = "tools";
    for (const t of tools) {
      const badge = document.createElement("span");
      badge.className = "tool-badge";
      //badge.textContent = `Consultó: ${NOMBRES_TOOLS[t] || t}`;
      badge.innerHTML = "<b>" + getTimeResponse() + "</b>";
      fila.appendChild(badge);
    }
    wrap.appendChild(fila);
  }*/

  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
  return wrap;
}

function getTimeResponse() {
  const now = new Date();
  const timeString = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return timeString;
  /*return `
    <div class="message-content">
      <span class="time">${timeString}</span>
    </div>
  `;*/
}

function mostrarEscribiendo() {
  const wrap = document.createElement("div");
  wrap.className = "msg bot typing";
  wrap.setAttribute("role", "status");
  wrap.setAttribute("aria-label", "El asistente está escribiendo");
  wrap.innerHTML = '<div class="bubble"><span></span><span></span><span></span></div>';
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
  return wrap;
}

function bloquear(valor) {
  enviando = valor;
  sendBtn.disabled = valor;
  sendBtn2.disabled = valor;
  chips.forEach((c) => (c.disabled = valor));
}

/* ---------- Envío ---------- */
async function enviar(texto) {
  texto = texto.trim();
  if (!texto || enviando) return;

  agregarMensaje("user", texto);
  input.value = "";
  input2.value = "";
  ajustarAltura();
  bloquear(true);
  escribiendoEl = mostrarEscribiendo();

  try {
    await canalListo; // la respuesta llegará por Pusher, así que el canal debe estar suscrito

    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message: texto }),
    });
    if (!res.ok) throw new Error("El servidor rechazó el mensaje.");

    // Si Pusher no entrega la respuesta a tiempo, liberamos el chat.
    temporizador = setTimeout(() => {
      terminarEspera();
      agregarMensaje("bot", "La respuesta tardó demasiado. Intenta de nuevo.", { error: true });
    }, TIEMPO_MAXIMO_MS);
  } catch (err) {
    terminarEspera();
    agregarMensaje("bot", err.message || "No hay conexión con el servidor.", { error: true });
  }
}

/* ---------- Eventos ---------- */
form.addEventListener("submit", (e) => {
  e.preventDefault();
  enviar(input.value);
});

// Enter envía; Shift+Enter agrega un salto de línea.
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    enviar(input.value);
  }
});

function ajustarAltura() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
}
input.addEventListener("input", ajustarAltura);

chips.forEach((chip) => chip.addEventListener("click", () => enviar(chip.dataset.text)));

resetBtn.addEventListener("click", async () => {
  try {
    await fetch("/api/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    });
  } catch (_) { /* si falla, igual limpiamos la vista */ }
  log.innerHTML = "";
  agregarMensaje("bot", MENSAJE_BIENVENIDA);
});

agregarMensaje("bot", MENSAJE_BIENVENIDA);

sendBtn2.addEventListener("click", () => {
  enviar(input2.value);
});
input2.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    enviar(input2.value);
  }
});