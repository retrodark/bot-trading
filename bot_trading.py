# ─────────────────────────────────────────────────────────
#  BOT DE TRADING - Multi-moneda sin hilos
#  Analiza cada vez que UptimeRobot hace ping (5 min)
#  Monedas: BTC, ETH, SOL, XRP | Fuente: Kraken
# ─────────────────────────────────────────────────────────

from flask import Flask, jsonify
import requests
import urllib.parse
import os
from datetime import datetime

app = Flask(__name__)

# ─────────────────────────────────────────
# CONFIGURACIÓN
# ─────────────────────────────────────────
WHATSAPP_NUMERO  = os.environ.get("WHATSAPP_NUMERO", "TU_NUMERO_AQUI")
CALLMEBOT_APIKEY = os.environ.get("CALLMEBOT_APIKEY", "TU_APIKEY_AQUI")

MONEDAS = {
    "Bitcoin  (BTC)":  "XBTUSD",
    "Ethereum (ETH)":  "ETHUSD",
    "Solana   (SOL)":  "SOLUSD",
    "XRP      (XRP)":  "XRPUSD",
}

INTERVALO   = 60
EMA_RAPIDA  = 9
EMA_LENTA   = 21
RSI_PERIODO = 14

# Guardamos última señal en memoria
ultimas_senales = {nombre: None for nombre in MONEDAS}

# Control de tiempo: solo analiza cada 30 minutos
ultimo_analisis = {"hora": None}

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


def obtener_precios(simbolo):
    url    = "https://api.kraken.com/0/public/OHLC"
    params = {"pair": simbolo, "interval": INTERVALO}
    try:
        r    = requests.get(url, params=params, timeout=15)
        data = r.json()
        if data.get("error"):
            print(f"[Kraken] Error en {simbolo}: {data['error']}")
            return None
        result = data.get("result", {})
        clave  = [k for k in result.keys() if k != "last"][0]
        velas  = result[clave]
        precios = [float(v[4]) for v in velas]
        print(f"[Kraken] {simbolo}: {len(precios)} velas | Precio: ${precios[-1]:,.4f}")
        return precios
    except Exception as e:
        print(f"[Kraken] Error en {simbolo}: {e}")
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


def analizar_moneda(nombre, simbolo):
    precios = obtener_precios(simbolo)
    if not precios or len(precios) < 30:
        print(f"[Bot] {nombre}: Sin datos.")
        return

    precio_actual = precios[-1]
    ema_r      = calcular_ema(precios,      EMA_RAPIDA)
    ema_l      = calcular_ema(precios,      EMA_LENTA)
    ema_r_prev = calcular_ema(precios[:-1], EMA_RAPIDA)
    ema_l_prev = calcular_ema(precios[:-1], EMA_LENTA)
    rsi        = calcular_rsi(precios,      RSI_PERIODO)

    print(f"[Bot] {nombre} | ${precio_actual:,.4f} | EMA9: {ema_r:.4f} | EMA21: {ema_l:.4f} | RSI: {rsi:.1f}")

    cruce_alcista = ema_r_prev < ema_l_prev and ema_r > ema_l
    cruce_bajista = ema_r_prev > ema_l_prev and ema_r < ema_l

    senal = None
    if cruce_alcista and rsi < 70:
        senal = "COMPRA"
    elif cruce_bajista and rsi > 30:
        senal = "VENTA"

    if senal and senal != ultimas_senales[nombre]:
        ultimas_senales[nombre] = senal
        emoji = "🟢" if senal == "COMPRA" else "🔴"
        emojis_moneda = {
            "Bitcoin  (BTC)": "₿",
            "Ethereum (ETH)": "Ξ",
            "Solana   (SOL)": "◎",
            "XRP      (XRP)": "✕",
        }
        hora = datetime.now().strftime("%d/%m/%Y %H:%M")
        mensaje = (
            f"{emoji} *SEÑAL DE {senal}*\n"
            f"{emojis_moneda.get(nombre, '🪙')} *Moneda: {nombre.strip()}*\n"
            f"💵 Precio: ${precio_actual:,.4f}\n"
            f"📈 EMA9: {ema_r:.4f} | EMA21: {ema_l:.4f}\n"
            f"📉 RSI: {rsi:.1f}\n"
            f"🕐 Hora: {hora}\n"
            f"─────────────────\n"
            f"⚠️ Recuerda gestionar tu riesgo."
        )
        print(f"[Bot] ¡Señal! {senal} en {nombre}")
        enviar_whatsapp(mensaje)
    else:
        print(f"[Bot] {nombre}: Sin señal nueva.")


def debe_analizar():
    """Retorna True solo si han pasado 30 minutos desde el último análisis."""
    ahora = datetime.now()
    if ultimo_analisis["hora"] is None:
        return True
    diferencia = (ahora - ultimo_analisis["hora"]).total_seconds()
    return diferencia >= 1800


def analizar_mercado():
    print(f"\n[Bot] ── Análisis: {datetime.now().strftime('%d/%m/%Y %H:%M')} ──")
    ultimo_analisis["hora"] = datetime.now()
    for nombre, simbolo in MONEDAS.items():
        analizar_moneda(nombre, simbolo)
    print("[Bot] ── Análisis completado ──\n")


# ─────────────────────────────────────────
# RUTAS
# ─────────────────────────────────────────

@app.route("/", methods=["GET"])
def inicio():
    """UptimeRobot llama a esta ruta cada 5 min.
    El bot analiza solo si han pasado 30 minutos."""
    if debe_analizar():
        analizar_mercado()
    else:
        print("[Bot] Ping recibido. Próximo análisis en breve.")
    return jsonify({"estado": "Bot activo ✅", "hora": str(datetime.now())}), 200


@app.route("/analizar", methods=["GET"])
def analizar_ahora():
    """Fuerza un análisis inmediato."""
    analizar_mercado()
    return jsonify({"estado": "Análisis completado ✅"}), 200


# ─────────────────────────────────────────
# INICIO
# ─────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Bot Multi-moneda iniciado en puerto {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
