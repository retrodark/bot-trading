# ─────────────────────────────────────────────────────────
#  BOT DE TRADING - Usa Kraken (sin límite de solicitudes)
#  Calcula EMA + RSI y manda señales por WhatsApp
#  Revisa cada 30 minutos con velas de 1 hora
# ─────────────────────────────────────────────────────────

from flask import Flask, jsonify
import requests
import urllib.parse
import os
from datetime import datetime
import threading
import time

app = Flask(__name__)

# ─────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────
WHATSAPP_NUMERO  = os.environ.get("WHATSAPP_NUMERO", "TU_NUMERO_AQUI")
CALLMEBOT_APIKEY = os.environ.get("CALLMEBOT_APIKEY", "TU_APIKEY_AQUI")

SIMBOLO     = "XBTUSD"   # BTC/USD en Kraken
INTERVALO   = 60          # 60 minutos = velas de 1 hora
EMA_RAPIDA  = 9
EMA_LENTA   = 21
RSI_PERIODO = 14

ultima_senal = {"accion": None}

# ─────────────────────────────────────────
# FUNCIONES MATEMÁTICAS
# ─────────────────────────────────────────

def calcular_ema(precios, periodo):
    k   = 2.0 / (periodo + 1)
    ema = precios[0]
    for precio in precios[1:]:
        ema = precio * k + ema * (1 - k)
    return ema


def calcular_rsi(precios, periodo=14):
    ganancias, perdidas = [], []
    for i in range(1, len(precios)):
        diff = precios[i] - precios[i - 1]
        if diff >= 0:
            ganancias.append(diff)
            perdidas.append(0)
        else:
            ganancias.append(0)
            perdidas.append(abs(diff))
    avg_gan = sum(ganancias[-periodo:]) / periodo
    avg_per = sum(perdidas[-periodo:])  / periodo
    if avg_per == 0:
        return 100
    return 100 - (100 / (1 + avg_gan / avg_per))


def obtener_precios():
    """Obtiene las últimas 200 velas de 1 hora desde Kraken."""
    url    = "https://api.kraken.com/0/public/OHLC"
    params = {"pair": SIMBOLO, "interval": INTERVALO}
    try:
        r    = requests.get(url, params=params, timeout=15)
        data = r.json()

        if data.get("error"):
            print(f"[Kraken] Error: {data['error']}")
            return None

        # Kraken devuelve los datos dentro de una clave dinámica
        result = data.get("result", {})
        clave  = [k for k in result.keys() if k != "last"][0]
        velas  = result[clave]

        # Cada vela: [time, open, high, low, close, vwap, volume, count]
        precios = [float(v[4]) for v in velas]  # usamos el precio de cierre
        print(f"[Kraken] {len(precios)} velas obtenidas. Último precio: ${precios[-1]:,.2f}")
        return precios

    except Exception as e:
        print(f"[Kraken] Error: {e}")
        return None


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
    print(f"[Bot] Analizando BTC/USD...")

    precios = obtener_precios()
    if not precios or len(precios) < 30:
        print("[Bot] No hay suficientes datos.")
        return

    precio_actual = precios[-1]
    ema_r      = calcular_ema(precios,      EMA_RAPIDA)
    ema_l      = calcular_ema(precios,      EMA_LENTA)
    ema_r_prev = calcular_ema(precios[:-1], EMA_RAPIDA)
    ema_l_prev = calcular_ema(precios[:-1], EMA_LENTA)
    rsi        = calcular_rsi(precios,      RSI_PERIODO)

    print(f"[Bot] Precio: ${precio_actual:,.2f} | EMA9: {ema_r:.2f} | EMA21: {ema_l:.2f} | RSI: {rsi:.1f}")

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
            f"📊 Par: BTCUSDT\n"
            f"💵 Precio: ${precio_actual:,.2f}\n"
            f"📈 EMA9: {ema_r:.2f} | EMA21: {ema_l:.2f}\n"
            f"📉 RSI: {rsi:.1f}\n"
            f"🕐 Hora: {hora}\n"
            f"─────────────────\n"
            f"⚠️ Recuerda gestionar tu riesgo."
        )
        print(f"[Bot] ¡Señal detectada! {senal}")
        enviar_whatsapp(mensaje)
    else:
        print("[Bot] Sin señal nueva.")


def loop_analisis():
    while True:
        analizar_mercado()
        time.sleep(1800)  # Revisa cada 30 minutos


# ─────────────────────────────────────────
# RUTAS
# ─────────────────────────────────────────

@app.route("/", methods=["GET"])
def inicio():
    return jsonify({"estado": "Bot activo ✅", "hora": str(datetime.now())}), 200


@app.route("/analizar", methods=["GET"])
def analizar_ahora():
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
