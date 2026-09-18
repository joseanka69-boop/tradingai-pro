# TradingAI Pro

Plataforma web de trading algorítmico con IA: señales en tiempo real,
Auto Trade (Paper y Real vía IBKR), alertas por WhatsApp, análisis con
Claude AI y noticias en vivo por instrumento.

## Estructura

```
tradingai/
├── main.py                 FastAPI app + WebSocket /ws
├── engine/                 Motor de señales, indicadores, auto trade, WhatsApp
├── routers/                Endpoints REST (/api/signals, /api/news, /api/ai, /api/autotrade, /api/alerts)
├── frontend/                Landing, dashboard y panel Auto Trade (HTML/CSS/JS puro)
└── data/                     Persistencia simple en JSON (suscriptores, usuarios auto trade)
```

## Instalación

```bash
python -m venv venv
source venv/bin/activate       # Mac/Linux
venv\Scripts\activate          # Windows

pip install -r requirements.txt

cp .env.example .env
# Completa tus claves en .env
```

## Ejecución

```bash
# Probar el scanner de forma aislada
python engine/scanner.py

# Levantar el servidor
uvicorn main:app --reload --port 8000

# Abrir el dashboard
# http://localhost:8000/frontend/dashboard.html
```

## Notas importantes

1. El scanner funciona aunque IBKR no esté conectado (usa yfinance como
   fallback para NQ=F).
2. El modo Auto Trade **Paper** no requiere IBKR — simula ejecución con
   precios reales del scanner.
3. El modo Auto Trade **Real** requiere `AUTOTRADE_MODE=real` en `.env`
   y una conexión activa a TWS/IB Gateway en el puerto 7496.
4. Las alertas de WhatsApp se envían de forma asíncrona y no bloquean
   el ciclo del scanner.
5. El WebSocket `/ws` emite el estado de todas las señales cada 30s.
6. El frontend es HTML/CSS/JS puro, sin frameworks — tema oscuro por defecto.

## Símbolos soportados

| Símbolo | Fuente de datos | TradingView |
|---|---|---|
| NQ  | IBKR (fallback yfinance `NQ=F`) | `CME_MINI:NQ1!` |
| MNQ | IBKR (fallback yfinance `MNQ=F`) | `CME_MINI:MNQ1!` |
| AMD | yfinance | `NASDAQ:AMD` |
| NVDA| yfinance | `NASDAQ:NVDA` |
| AAPL| yfinance | `NASDAQ:AAPL` |
| TSLA| yfinance | `NASDAQ:TSLA` |
| BTC | Binance (`BTCUSDT`) | `BITSTAMP:BTCUSD` |
| ETH | Binance (`ETHUSDT`) | `BITSTAMP:ETHUSD` |

## Lógica de señal (triple certificación)

```
LONG  : Z-Score <= -2.0  AND RSI <= 30  AND Precio <= BB_Lower AND ADX < 30
SHORT : Z-Score >= +2.0  AND RSI >= 70  AND Precio >= BB_Upper AND ADX < 30
SALIDA: Z-Score cruza 0 (reversión a la media)
STOP  : 2.5 × ATR dinámico
```

## Aviso de riesgo

Este software es solo con fines educativos e informativos. El trading de
futuros, acciones y criptomonedas conlleva un riesgo sustancial de pérdida.
El modo Real ejecuta órdenes reales contra tu cuenta de IBKR — actívalo
bajo tu propia responsabilidad y con capital que puedas permitirte perder.
