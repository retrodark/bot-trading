# ─────────────────────────────────────────────────────────
#  BOT DE TRADING - Servidor Webhook
#  Recibe alertas de TradingView y manda WhatsApp
# ─────────────────────────────────────────────────────────
#  Instalación: pip install flask requests
#  Ejecución local: python bot_trading.py
# ─────────────────────────────────────────────────────────

from flask import Flask, request, jsonify
import requests
import urllib.parse
import os
from datetime import datetime

app = Flask(__name__)

# ─────────────────────────────────────────
# CONFIGURACIÓN — Edita estos valores
# ─────────────────────────────────────────

# 1. Tu número de WhatsApp con código de país (sin + ni espacios)
#    Ejemplo El Salvador: 50312345678
WHATSAPP_NUMERO = os.environ.get("WHATSAPP_NUMERO", "TU_NUMERO_AQUI")

# 2. Tu API Key de CallMeBot (la obtienes en el paso 3 de la guía)
CALLMEBOT_APIKEY = os.environ.get("CALLMEBOT_APIKEY", "TU_APIKEY_AQUI")

# 3. Token secreto para que solo TradingView pueda usar tu servidor
WEBHOOK_TOKEN = os.environ.get("WEBHOOK_TOKEN", "mi_token_secreto_123")

# ─────────────────────────────────────────

def enviar_whatsapp(mensaje: str):
    """Envía un mensaje de WhatsApp usando CallMeBot."""
    mensaje_codificado = urllib.parse.quote(mensaje)
    url = (
        f"https://api.callmebot.com/whatsapp.php"
        f"?phone={WHATSAPP_NUMERO}"
        f"&text={mensaje_codificado}"
        f"&apikey={CALLMEBOT_APIKEY}"
    )
    try:
        respuesta = requests.get(url, timeout=10)
        print(f"[WhatsApp] Status: {respuesta.status_code}")
        return respuesta.status_code == 200
    except Exception as e:
        print(f"[WhatsApp] Error: {e}")
        return False


def formatear_mensaje(datos: dict) -> str:
    """Convierte los datos del webhook en un mensaje legible."""
    accion  = datos.get("accion", "DESCONOCIDO")
    simbolo = datos.get("simbolo", "???")
    precio  = datos.get("precio", "???")
    tiempo  = datos.get("tiempo", datetime.now().strftime("%Y-%m-%d %H:%M"))

    emoji = "🟢" if accion == "COMPRA" else "🔴"

    return (
        f"{emoji} *SEÑAL DE {accion}*\n"
        f"📊 Par: {simbolo}\n"
        f"💵 Precio: ${float(precio):,.2f}\n"
        f"🕐 Hora: {tiempo}\n"
        f"─────────────────\n"
        f"⚠️ Recuerda gestionar tu riesgo."
    )


# ─────────────────────────────────────────
# RUTAS DEL SERVIDOR
# ─────────────────────────────────────────

@app.route("/", methods=["GET"])
def inicio():
    return jsonify({"estado": "Bot activo ✅", "hora": str(datetime.now())}), 200


@app.route("/webhook/<token>", methods=["POST"])
def webhook(token):
    # Verificar token de seguridad
    if token != WEBHOOK_TOKEN:
        print("[Seguridad] Token inválido recibido.")
        return jsonify({"error": "No autorizado"}), 403

    # Leer datos enviados por TradingView
    datos = request.get_json(silent=True)
    if not datos:
        return jsonify({"error": "JSON inválido"}), 400

    print(f"[Webhook] Señal recibida: {datos}")

    # Formatear y enviar mensaje
    mensaje = formatear_mensaje(datos)
    exito   = enviar_whatsapp(mensaje)

    if exito:
        return jsonify({"estado": "Mensaje enviado ✅"}), 200
    else:
        return jsonify({"estado": "Error al enviar mensaje ❌"}), 500


# ─────────────────────────────────────────
# INICIO
# ─────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Servidor iniciado en puerto {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
