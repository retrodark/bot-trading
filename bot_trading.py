# ─────────────────────────────────────────────────────────
#  BOT DE TRADING - Consulta Binance directamente
#  Calcula EMA + RSI y manda señales por WhatsApp
# ─────────────────────────────────────────────────────────

from flask import Flask, jsonify
import requests
import urllib.parse
import os
import pandas as pd
from datetime import datetime
import threading
import time

app = Flask(__name__)

# ─────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────
WHATSAPP_NUMERO  = os.environ.get("WHATSAPP_NUMERO", "TU_NUMERO_AQUI")
CALLMEBOT_APIKEY = os.environ.get("CALLMEBOT_APIKEY", "TU_APIKEY_AQUI")

SIMBOLO     = "BTCUSDT"
INTERVALO   = "1h"
EMA_RAPIDA  = 9
EMA_LENTA   = 21
RSI_PERIODO = 14

ultima_senal = {"accion": None}

# ─────────────────────────────────────────
# FUNCIONES
# ─────────────────────────────────────────

def obtener_velas():
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": SIMBOLO, "interval": INTERVALO, "limit": 100}
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        return [float(v[4]) for v in data]
    except Exception as e:
        print(f"[Binance] Error: {e}")
        return None


def calcular_ema(precios, periodo):
    return pd.Series(precios).ewm(span=periodo, adjust=False).mean().iloc[-1]


def calcular_rsi(precios, periodo=14):
    serie  = pd.Series(precios)
    delta  = serie.diff()
    ganancia = delta.where(delta > 0, 0).rolling(periodo).mean()
    perdida  = (-delta.where(delta < 0, 0)).rolling(periodo).mean()
    rs  = ganancia / perdida
    return (100 - (100 / (1 + rs))).iloc[-1]


def enviar_whatsapp(mensaje: str):
    mensaje_codificado = urllib.parse.quote(mensaje)
    url = (
        f"https://api.callmebot.com/whatsapp.php"
        f"?phone={WHATSAPP_NUMERO}"
        f"&text={mensaje_codificado}"
        f"&apikey={CALLMEBOT_APIKEY}"
    )
    try:
        r = requests.get(url, timeout=10)
        print(f"[WhatsApp] Status: {r.status_code}")
        return r.status_code == 200
    except Exception as e:
        print(f"[WhatsApp] Error: {e}")
        return False


def analizar_mercado():
    global ultima_senal
    print(f"[Bot] Analizando {SIMBOLO}...")

    precios = obtener_velas()
    if not precios or len(precios) < 30:
        print("[Bot] No hay suficientes datos.")
        return

    precio_actual = precios[-1]
    ema_r      = calcular_ema(precios,      EMA_RAPIDA)
    ema_l      = calcular_ema(precios,      EMA_LENTA)
    ema_r_prev = calcular_ema(precios[:-1], EMA_RAPIDA)
    ema_l_prev = calcular_ema(precios[:-1], EMA_LENTA)
    rsi        = calcular_rsi(precios,      RSI_PERIODO)

    print(f"[Bot] Precio: {precio_actual:.2f} | EMA9: {ema_r:.2f} | EMA21: {ema_l:.2f} | RSI: {rsi:.1f}")

    cruce_alcista = ema_r_prev < ema_l_prev and ema_r > ema_l
    cruce_bajista = ema_r_prev > ema_l_prev and ema_r < ema_l

    senal = None
    if cruce_alcista and rsi < 70:
        senal = "COMPRA"
    elif cruce_bajista and rsi > 30:
        senal = "VENTA"

    if senal and senal != ultima_senal["accion"]:
        ultima_senal["accion"] = senal
        emoji = "🟢" if senal == "COMPRA" else "🔴"
        hora  = datetime.now().strftime("%d/%m/%Y %H:%M")

        mensaje = (
            f"{emoji} *SEÑAL DE {senal}*\n"
            f"📊 Par: {SIMBOLO}\n"
            f"💵 Precio: ${precio_actual:,.2f}\n"
            f"📈 EMA9: {ema_r:.2f} | EMA21: {ema_l:.2f}\n"
            f"📉 RSI: {rsi:.1f}\n"
            f"🕐 Hora: {hora}\n"
            f"─────────────────\n"
            f"⚠️ Recuerda gestionar tu riesgo."
        )
        print(f"[Bot] Señal detectada: {senal}")
        enviar_whatsapp(mensaje)
    else:
        print("[Bot] Sin señal nueva.")


def loop_analisis():
    while True:
        analizar_mercado()
        time.sleep(3600)


# ─────────────────────────────────────────
# RUTAS
# ─────────────────────────────────────────

@app.route("/", methods=["GET"])
def inicio():
    return jsonify({"estado": "Bot activo ✅", "hora": str(datetime.now())}), 200


@app.route("/analizar", methods=["GET"])
def analizar_ahora():
    """Llama a esta URL para forzar un análisis inmediato y probar."""
    analizar_mercado()
    return jsonify({"estado": "Análisis completado ✅"}), 200


# ─────────────────────────────────────────
# INICIO
# ─────────────────────────────────────────

if __name__ == "__main__":
    hilo = threading.Thread(target=loop_analisis, daemon=True)
    hilo.start()

    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Bot iniciado en puerto {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
