# ─────────────────────────────────────────────────────────
#  BOT DE TRADING AVANZADO - Multi-moneda
#  Estrategia: EMA + RSI + MACD + ATR
#  Incluye: Precio entrada, Take Profit, Stop Loss
#  Zona horaria: El Salvador (UTC-6)
# ─────────────────────────────────────────────────────────

from flask import Flask, jsonify
import requests
import urllib.parse
import os
from datetime import datetime, timezone, timedelta

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

INTERVALO   = 60   # velas de 1 hora
EMA_RAPIDA  = 9
EMA_LENTA   = 21
RSI_PERIODO = 14
MACD_RAPIDA = 12
MACD_LENTA  = 26
MACD_SEÑAL  = 9
ATR_PERIODO = 14

# Take Profit y Stop Loss basados en ATR
TP_MULTIPLICADOR = 2.0   # Take Profit = entrada ± 2x ATR
SL_MULTIPLICADOR = 1.0   # Stop Loss   = entrada ∓ 1x ATR

# Zona horaria El Salvador (UTC-6)
TZ_SLV = timezone(timedelta(hours=-6))

ultimas_senales  = {nombre: None for nombre in MONEDAS}
ultimo_analisis  = {"hora": None}

# ─────────────────────────────────────────
# FUNCIONES MATEMÁTICAS
# ─────────────────────────────────────────

def hora_elsalvador():
    """Retorna la hora actual en El Salvador."""
    return datetime.now(TZ_SLV).strftime("%d/%m/%Y %I:%M %p")


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


def calcular_macd(precios):
    """Calcula MACD, línea de señal e histograma."""
    ema_r  = [calcular_ema(precios[:i+1], MACD_RAPIDA) for i in range(len(precios)) if i >= MACD_RAPIDA]
    ema_l  = [calcular_ema(precios[:i+1], MACD_LENTA)  for i in range(len(precios)) if i >= MACD_LENTA]
    n      = min(len(ema_r), len(ema_l))
    macd_line  = [ema_r[-n+i] - ema_l[-n+i] for i in range(n)]
    señal_line = [calcular_ema(macd_line[:i+1], MACD_SEÑAL) for i in range(len(macd_line)) if i >= MACD_SEÑAL]
    if not señal_line:
        return None, None, None
    hist    = macd_line[-1] - señal_line[-1]
    hist_prev = macd_line[-2] - señal_line[-2] if len(señal_line) >= 2 else hist
    return macd_line[-1], señal_line[-1], hist, hist_prev


def calcular_atr(velas, periodo=14):
    """Calcula el ATR (Average True Range) para definir TP y SL."""
    true_ranges = []
    for i in range(1, len(velas)):
        high  = float(velas[i][2])
        low   = float(velas[i][3])
        close_prev = float(velas[i-1][4])
        tr = max(high - low, abs(high - close_prev), abs(low - close_prev))
        true_ranges.append(tr)
    if len(true_ranges) < periodo:
        return None
    return sum(true_ranges[-periodo:]) / periodo


def obtener_datos(simbolo):
    """Obtiene velas de Kraken con datos OHLC completos."""
    url    = "https://api.kraken.com/0/public/OHLC"
    params = {"pair": simbolo, "interval": INTERVALO}
    try:
        r    = requests.get(url, params=params, timeout=15)
        data = r.json()
        if data.get("error"):
            print(f"[Kraken] Error en {simbolo}: {data['error']}")
            return None, None
        result = data.get("result", {})
        clave  = [k for k in result.keys() if k != "last"][0]
        velas  = result[clave]
        precios = [float(v[4]) for v in velas]
        print(f"[Kraken] {simbolo}: {len(precios)} velas | ${precios[-1]:,.4f}")
        return precios, velas
    except Exception as e:
        print(f"[Kraken] Error en {simbolo}: {e}")
        return None, None


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
    precios, velas = obtener_datos(simbolo)
    if not precios or not velas or len(precios) < 50:
        print(f"[Bot] {nombre}: Sin datos suficientes.")
        return

    precio_actual = precios[-1]

    # ── Indicadores ──────────────────────────
    ema_r      = calcular_ema(precios,      EMA_RAPIDA)
    ema_l      = calcular_ema(precios,      EMA_LENTA)
    ema_r_prev = calcular_ema(precios[:-1], EMA_RAPIDA)
    ema_l_prev = calcular_ema(precios[:-1], EMA_LENTA)
    rsi        = calcular_rsi(precios,      RSI_PERIODO)
    atr        = calcular_atr(velas,        ATR_PERIODO)
    resultado_macd = calcular_macd(precios)

    if resultado_macd[0] is None or atr is None:
        print(f"[Bot] {nombre}: Datos insuficientes para MACD/ATR.")
        return

    macd_val, señal_val, hist, hist_prev = resultado_macd

    # ── Condiciones de entrada ────────────────
    cruce_alcista = ema_r_prev < ema_l_prev and ema_r > ema_l
    cruce_bajista = ema_r_prev > ema_l_prev and ema_r < ema_l
    macd_alcista  = hist > 0 and hist_prev <= 0   # MACD cruza hacia arriba
    macd_bajista  = hist < 0 and hist_prev >= 0   # MACD cruza hacia abajo

    print(f"[Bot] {nombre} | RSI: {rsi:.1f} | MACD hist: {hist:.4f} | ATR: {atr:.4f}")

    # ── Señal LONG (compra) ───────────────────
    # Condición: EMA cruza al alza + MACD positivo + RSI entre 40-65 (momentum sin sobrecompra)
    es_long  = cruce_alcista and macd_alcista and 40 <= rsi <= 65

    # ── Señal SHORT (venta) ───────────────────
    # Condición: EMA cruza a la baja + MACD negativo + RSI entre 35-60
    es_short = cruce_bajista and macd_bajista and 35 <= rsi <= 60

    senal = None
    if es_long:
        senal = "LONG"
    elif es_short:
        senal = "SHORT"

    if senal and senal != ultimas_senales[nombre]:
        ultimas_senales[nombre] = senal

        # ── Precios de entrada, TP y SL ──────────
        entrada = precio_actual
        if senal == "LONG":
            take_profit = entrada + (atr * TP_MULTIPLICADOR)
            stop_loss   = entrada - (atr * SL_MULTIPLICADOR)
            emoji       = "🟢"
            direccion   = "📈 LONG (COMPRA)"
        else:
            take_profit = entrada - (atr * TP_MULTIPLICADOR)
            stop_loss   = entrada + (atr * SL_MULTIPLICADOR)
            emoji       = "🔴"
            direccion   = "📉 SHORT (VENTA)"

        emojis_moneda = {
            "Bitcoin  (BTC)": "₿",
            "Ethereum (ETH)": "Ξ",
            "Solana   (SOL)": "◎",
            "XRP      (XRP)": "✕",
        }

        # Ratio riesgo/beneficio
        riesgo    = abs(entrada - stop_loss)
        beneficio = abs(take_profit - entrada)
        ratio     = beneficio / riesgo if riesgo > 0 else 0

        hora = hora_elsalvador()

        mensaje = (
            f"{emoji} *{direccion}*\n"
            f"{emojis_moneda.get(nombre, '🪙')} *{nombre.strip()}*\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"💵 *Entrada:*     ${entrada:,.4f}\n"
            f"🎯 *Take Profit:* ${take_profit:,.4f}\n"
            f"🛑 *Stop Loss:*   ${stop_loss:,.4f}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📊 RSI: {rsi:.1f} | MACD: {macd_val:.4f}\n"
            f"📐 Ratio R/B: 1:{ratio:.1f}\n"
            f"🕐 {hora} (El Salvador)\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"⚠️ Gestiona tu riesgo siempre."
        )
        print(f"[Bot] ¡Señal {senal} en {nombre}! TP: {take_profit:.4f} | SL: {stop_loss:.4f}")
        enviar_whatsapp(mensaje)
    else:
        print(f"[Bot] {nombre}: Sin señal nueva.")


def analizar_mercado():
    print(f"\n[Bot] ── Análisis: {hora_elsalvador()} ──")
    ultimo_analisis["hora"] = datetime.now()
    for nombre, simbolo in MONEDAS.items():
        analizar_moneda(nombre, simbolo)
    print("[Bot] ── Análisis completado ──\n")


def debe_analizar():
    ahora = datetime.now()
    if ultimo_analisis["hora"] is None:
        return True
    return (ahora - ultimo_analisis["hora"]).total_seconds() >= 1800


# ─────────────────────────────────────────
# RUTAS
# ─────────────────────────────────────────

@app.route("/", methods=["GET"])
def inicio():
    if debe_analizar():
        analizar_mercado()
    else:
        print("[Bot] Ping recibido. Esperando próximo análisis.")
    return jsonify({"estado": "Bot activo ✅", "hora": hora_elsalvador()}), 200


@app.route("/analizar", methods=["GET"])
def analizar_ahora():
    analizar_mercado()
    return jsonify({"estado": "Análisis completado ✅"}), 200


# ─────────────────────────────────────────
# INICIO
# ─────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Bot Avanzado iniciado en puerto {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
