"""
Servidor MCP (librería FastMCP, transporte stdio) con 5 herramientas para el chatbot:
  1. saludo
  2. horario_atencion
  3. medios_de_pago
  4. informacion_empresa
  5. reserva_de_citas
  6. lista_de_facturas
  7. lista_de_categorias
  8. lista_de_productos_por_categoria
  9. lista_de_servicios

IMPORTANTE: un servidor stdio no debe escribir nada en stdout (print),
porque ese canal se usa para el protocolo MCP. Para depurar usa stderr.
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from fastmcp import FastMCP
import requests
import json

mcp = FastMCP("joyeria-dgala")

# --------------------------------------------------------------------------
# Datos de la empresa (edítalos con tu información real)
# --------------------------------------------------------------------------
ZONA_HORARIA = os.getenv("EMPRESA_TZ", "America/Bogota")

EMPRESA = {
    "nombre": "Joyería D'Gala",
    "descripcion": (
        "La joyería D’Gala es una empresa que realiza fabricación, restauración y venta al por mayor y menor," 
        "de productos enfocados en la joyería artesanal siendo de oro y plata"
    ),
    "fundacion": "2024",
    "direccion": "MZ. D LT 12 ASOC. DE PRO - LIMA-Lima-PUENTE PIEDRA",
    "telefono": "+51 916520052",
    "whatsapp": "+51 916520052",
    "correo": "tmarino420@gmail.com",
    "sitio_web": "https://www.joyeriadgala.com",
}

# 0 = lunes ... 6 = domingo. Valor: (hora_apertura, hora_cierre) o None si cierra.
HORARIO = {
    0: (8, 18),
    1: (8, 18),
    2: (8, 18),
    3: (8, 18),
    4: (8, 18),
    5: (9, 14),
    6: None,
}
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

MEDIOS_PAGO = [
    "Tarjetas de crédito (Visa, Mastercard, Dinners Club)",
    "Tarjetas débito",
    "Transferencia bancaria directa",
    "Efectivo en tienda física",
    "Contra entrega en Lima",
]


def _formato_hora(hora: int) -> str:
    return f"{hora:02d}:00"


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------
@mcp.tool
def saludo(nombre: str = "") -> str:
    """Devuelve un saludo de bienvenida según la hora del día.

    Úsala cuando el usuario salude (hola, buenos días, buenas tardes...) o
    inicie la conversación. Si conoces el nombre del usuario, pásalo en `nombre`.

    Args:
        nombre: Nombre del usuario (opcional).
    """
    ahora = datetime.now(ZoneInfo(ZONA_HORARIA))
    if ahora.hour < 12:
        momento = "Buenos días"
    elif ahora.hour < 19:
        momento = "Buenas tardes"
    else:
        momento = "Buenas noches"

    persona = f", {nombre.strip()}" if nombre and nombre.strip() else ""
    return (
        f"{momento}{persona}. Te damos la bienvenida a {EMPRESA['nombre']}. "
        "Puedo ayudarte con nuestro horario de atención, medios de pago "
        "e información de la empresa."
    )


@mcp.tool
def horario_atencion() -> str:
    """Devuelve el horario de atención de la empresa y si está abierta en este momento.

    Úsala cuando pregunten a qué hora abren o cierran, qué días atienden,
    o si la empresa está abierta ahora.
    """
    ahora = datetime.now(ZoneInfo(ZONA_HORARIA))
    hoy = HORARIO[ahora.weekday()]

    lineas = []
    for indice, dia in enumerate(DIAS):
        tramo = HORARIO[indice]
        if tramo is None:
            lineas.append(f"- {dia.capitalize()}: cerrado")
        else:
            lineas.append(
                f"- {dia.capitalize()}: {_formato_hora(tramo[0])} a {_formato_hora(tramo[1])}"
            )

    if hoy is None:
        estado = "Hoy la empresa permanece cerrada."
    elif hoy[0] <= ahora.hour < hoy[1]:
        estado = f"Ahora mismo estamos abiertos (cerramos hoy a las {_formato_hora(hoy[1])})."
    else:
        estado = "Ahora mismo estamos cerrados."

    return (
        f"Horario de atención de {EMPRESA['nombre']} (zona horaria {ZONA_HORARIA}):\n"
        + "\n".join(lineas)
        + f"\n\nEstado actual: {estado}"
    )


@mcp.tool
def medios_de_pago() -> str:
    """Devuelve los medios de pago que acepta la empresa.

    Úsala cuando pregunten cómo se puede pagar, si aceptan tarjeta,
    transferencias, efectivo, pago contra entrega, cuotas, etc.
    """
    lista = "\n".join(f"- {medio}" for medio in MEDIOS_PAGO)
    return f"Medios de pago disponibles en {EMPRESA['nombre']}:\n{lista}"


@mcp.tool
def informacion_empresa() -> str:
    """Devuelve información general de la empresa: qué hace, dirección y datos de contacto.

    Úsala cuando pregunten quiénes son, a qué se dedican, dónde están ubicados,
    o cómo contactarlos (teléfono, WhatsApp, correo, sitio web).
    """
    return (
        f"{EMPRESA['nombre']}\n"
        f"- Descripción: {EMPRESA['descripcion']}\n"
        f"- Fundada en: {EMPRESA['fundacion']}\n"
        f"- Dirección: {EMPRESA['direccion']}\n"
        f"- Teléfono: {EMPRESA['telefono']}\n"
        f"- WhatsApp: {EMPRESA['whatsapp']}\n"
        f"- Correo: {EMPRESA['correo']}\n"
        f"- Sitio web: {EMPRESA['sitio_web']}"
    )

@mcp.tool
def reserva_de_citas() -> str:
    """
    Devuelve enlace para realizar reserva de citas para un servicio personalizado.

    Úsala cuando te pregunten, deseo realizar una coordinacion de un servicio personalizado de joyería. quiero personalizar un servicio de joya,
    deseo saber como es el servicio especial para una joya, quiero agendar una cita para un servicio especial, 
    """
    return (
        "Reserva tu cita en Joyería D'Gala:\n"
        "Agenda una visita para recibir asesorías personalizadas, diseño a medida, "
        "restauración de joyas o compra de piezas artesanales en oro y plata. "
        "Atención de 9:00 AM a 18:00 PM.\n\n"
        "https://dgala2026.alwaysdata.net/calendly"
    )

@mcp.tool
def lista_de_facturas() -> str:
    """
    Devuelve la lista de facturas de todas las compras que el cliente realizó.

    Úsala cuando te pregunten sobre lista de facturas, mis compras realizadas.
    """
    url = "https://dgala2026.alwaysdata.net/api/v1/invoices/2"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return (json.dumps(data))
    else:
        return (f"Error en la petición: {response.status_code}")


@mcp.tool
def lista_de_categorias() -> str:
    """
    Devuelve la lista de categorias disponibles
    Úsala cuando te pregunten sobre lista de categorias, que categorías tienes disponible, que categorías tiene la empresa o que categorías tienes.
    """
    url = "https://dgala2026.alwaysdata.net/api/v1/categories/list"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return (json.dumps(data))
    else:
        return (f"Error en la petición: {response.status_code}")


@mcp.tool
def lista_de_productos_por_categoria(categoria: str) -> str:
    """
    Devuelve la lista de productos por categoria
    Úsala cuando el usuario solicita la lista de productos de categoría, por ejemplo "Puedes mostrarme los productos de Anillos",
    "Listame los productos de Medallas", "Muestrame los productos de Aretes", "Qué productos tienes disponible de Cadenas", "Tienes productos de Cadenas"
    "que productos tienes por categoría Anillos", "que productos tieines disponibles de Aretes", "lista de productos por categoría Anillos"
    
    Args:
        categoria: Nombre de categoría al que se va a filtrar.
    """
    categoria = (categoria or "").strip()
    
    url = f"https://dgala2026.alwaysdata.net/api/v1/products/list/{categoria}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return (json.dumps(data))
    else:
        return (f"Error en la petición: {response.status_code}")

@mcp.tool
def lista_de_servicios() -> str:
    """Devuelve la lista de servicios que ofrece o realiza la empresa.

    Úsala cuando pregunten que servicios ofrece o que tipos de servicios ofrece.
    """
    return (
        "Lista de Servicios:\n"
        "- Mantenimiento de Joya\n"
        "- Grabado\n"
        "- Diseño\n"
        "- Ajuste de Talla\n"
        "- Engaste de Diamante\n"
        "- Pasado de Perlas\n"
        "- Restauración"
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
