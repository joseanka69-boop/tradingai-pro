/**
 * Lógica del dashboard: cambio de símbolo, gráfico TradingView, pestañas
 * (Señales / Noticias / IA / Stats) y actualización en tiempo real vía WebSocket.
 */

const TV_SYMBOLS = {
  NQ: "CME_MINI:NQ1!",
  MNQ: "CME_MINI:MNQ1!",
  AMD: "NASDAQ:AMD",
  NVDA: "NASDAQ:NVDA",
  AAPL: "NASDAQ:AAPL",
  TSLA: "NASDAQ:TSLA",
  MSFT: "NASDAQ:MSFT",
  GOOGL: "NASDAQ:GOOGL",
  META: "NASDAQ:META",
  AMZN: "NASDAQ:AMZN",
  NFLX: "NASDAQ:NFLX",
  BTC: "BITSTAMP:BTCUSD",
  ETH: "BITSTAMP:ETHUSD",
};

const WATCHLIST_SYMBOLS = Object.keys(TV_SYMBOLS);

let currentSymbol = "NQ";
let currentInterval = "5";
let latestSignals = {};
let tvWidget = null;

function renderChart() {
  const container = document.getElementById("tv-chart");
  container.innerHTML = "";
  tvWidget = new TradingView.widget({
    container_id: "tv-chart",
    autosize: true,
    symbol: TV_SYMBOLS[currentSymbol] || TV_SYMBOLS.NQ,
    interval: currentInterval,
    theme: "dark",
    style: "1",
    locale: "es",
    toolbar_bg: "#111826",
    enable_publishing: false,
    hide_top_toolbar: false,
    studies: ["RSI@tv-basicstudies", "BB@tv-basicstudies"],
  });
}

function setSymbol(symbol) {
  currentSymbol = symbol;
  renderChart();
  renderSignalPanel();
  loadNews();
  syncSymbolControls();
}

function syncSymbolControls() {
  const select = document.getElementById("symbol-select");
  if (select) select.value = currentSymbol;

  document.querySelectorAll(".nav-symbol-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.symbol === currentSymbol);
  });
  document.querySelectorAll(".watchlist-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.symbol === currentSymbol);
  });
}

function renderWatchlist() {
  const el = document.getElementById("watchlist");
  el.innerHTML = WATCHLIST_SYMBOLS.map((sym) => `
    <button class="watchlist-btn ${sym === currentSymbol ? "active" : ""}" data-symbol="${sym}" title="${sym}">${sym}</button>
  `).join("");
  el.querySelectorAll(".watchlist-btn").forEach((btn) => {
    btn.addEventListener("click", () => setSymbol(btn.dataset.symbol));
  });
}

function setInterval_(interval, btn) {
  currentInterval = interval;
  document.querySelectorAll(".tf-btn").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  renderChart();
}

function switchTab(tabName) {
  document.querySelectorAll(".panel-tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tabName));
  document.querySelectorAll(".panel-view").forEach((v) => v.classList.toggle("active", v.id === `view-${tabName}`));
  if (tabName === "news") loadNews();
  if (tabName === "stats") loadStats();
}

function pct(value, min, max) {
  const clamped = Math.max(min, Math.min(max, value));
  return ((clamped - min) / (max - min)) * 100;
}

function renderSignalPanel() {
  const el = document.getElementById("view-signals");
  const s = latestSignals[currentSymbol];

  if (!s) {
    el.innerHTML = `<div class="text-dim">Sin datos aún para ${currentSymbol}. Esperando al motor de señales…</div>`;
    return;
  }

  const badgeClass = s.direction === "LONG" ? "badge-long" : s.direction === "SHORT" ? "badge-short" : "badge-neutral";

  el.innerHTML = `
    <div class="card" style="margin-bottom:16px;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div style="font-size:22px;font-weight:700;">${s.price}</div>
        <div class="badge ${badgeClass}">${s.direction}</div>
      </div>
      <div class="text-dim" style="font-size:12px;">${currentSymbol}</div>
    </div>

    <div class="indicator-row">
      <div class="label"><span>RSI</span><span>${s.rsi}</span></div>
      <div class="indicator-bar-bg"><div class="indicator-bar-fill" style="width:${pct(s.rsi, 0, 100)}%"></div></div>
    </div>
    <div class="indicator-row">
      <div class="label"><span>Z-Score</span><span>${s.zscore}</span></div>
      <div class="indicator-bar-bg"><div class="indicator-bar-fill" style="width:${pct(s.zscore, -3, 3)}%"></div></div>
    </div>
    <div class="indicator-row">
      <div class="label"><span>ADX</span><span>${s.adx}</span></div>
      <div class="indicator-bar-bg"><div class="indicator-bar-fill" style="width:${pct(s.adx, 0, 60)}%"></div></div>
    </div>
    <div class="indicator-row">
      <div class="label"><span>ATR</span><span>${s.atr}</span></div>
    </div>

    <div class="text-dim" style="font-size:12px;margin-top:12px;">
      Bandas de Bollinger: ${s.bb_lower} — ${s.bb_mid} — ${s.bb_upper}
    </div>

    ${s.stop_loss ? `
    <div class="sl-tp-box">
      <div class="sl">SL: ${s.stop_loss}</div>
      <div class="tp">TP: ${s.take_profit}</div>
    </div>` : ""}
  `;
}

async function loadNews() {
  const el = document.getElementById("view-news");
  el.innerHTML = `<div class="text-dim">Cargando noticias de ${currentSymbol}…</div>`;
  try {
    const res = await fetch(`/api/news/${currentSymbol}`);
    const data = await res.json();
    if (!data.articles || data.articles.length === 0) {
      el.innerHTML = `<div class="text-dim">${data.error || "Sin noticias disponibles."}</div>`;
      return;
    }
    el.innerHTML = data.articles.map((a) => `
      <div class="news-item">
        <a href="${a.url}" target="_blank" rel="noopener">${a.title}</a>
        <div class="meta">${a.source || ""} · ${a.published_at ? new Date(a.published_at).toLocaleString() : ""}</div>
      </div>
    `).join("");
  } catch (e) {
    el.innerHTML = `<div class="text-dim">No se pudieron cargar las noticias.</div>`;
  }
}

function appendAiMessage(role, text) {
  const messages = document.getElementById("ai-messages");
  const div = document.createElement("div");
  div.className = `ai-msg ${role}`;
  div.textContent = text;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

async function sendAiQuestion() {
  const input = document.getElementById("ai-input");
  const question = input.value.trim();
  if (!question) return;

  appendAiMessage("user", question);
  input.value = "";
  appendAiMessage("assistant", "Analizando…");
  const messages = document.getElementById("ai-messages");

  try {
    const res = await fetch("/api/ai/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol: currentSymbol, question }),
    });
    const data = await res.json();
    messages.lastChild.remove();
    appendAiMessage("assistant", data.analysis || data.error || "Sin respuesta.");
  } catch (e) {
    messages.lastChild.remove();
    appendAiMessage("assistant", "Error al conectar con el servidor de IA.");
  }
}

function getSelectedBroker() {
  return localStorage.getItem("tradingai_broker") || "ibkr";
}

function setSelectedBroker(broker) {
  localStorage.setItem("tradingai_broker", broker);
  document.querySelectorAll(".broker-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.broker === broker);
  });
}

async function loadBrokerSelector() {
  const statusEl = document.getElementById("broker-status");
  try {
    const res = await fetch("/api/brokers");
    const data = await res.json();
    document.querySelectorAll(".broker-btn").forEach((btn) => {
      const brokerStatus = data.status[btn.dataset.broker] || "unknown";
      btn.dataset.status = brokerStatus;
    });
    statusEl.textContent = `IBKR: ${data.status.ibkr} · Alpaca: ${data.status.alpaca}`;
  } catch (e) {
    statusEl.textContent = "No se pudo consultar el estado de los brokers.";
  }
  setSelectedBroker(getSelectedBroker());
}

async function loadStats() {
  const el = document.getElementById("stats-dynamic");
  el.innerHTML = `<div class="text-dim">Cargando estadísticas…</div>`;
  try {
    const userId = localStorage.getItem("tradingai_user_id");
    if (!userId) {
      el.innerHTML = `<div class="text-dim">Activa tu Auto Trade en el panel correspondiente para ver estadísticas. <a href="autotrade.html">Ir al panel</a></div>`;
      return;
    }
    const res = await fetch(`/api/autotrade/user/${userId}`);
    const user = await res.json();
    const trades = user.closed_trades || [];
    const wins = trades.filter((t) => t.pnl > 0).length;
    const winRate = trades.length ? ((wins / trades.length) * 100).toFixed(1) : "0.0";
    const totalPnl = trades.reduce((acc, t) => acc + t.pnl, 0).toFixed(2);

    el.innerHTML = `
      <div class="stats-grid">
        <div class="stat-box"><div class="val">${winRate}%</div><div class="lbl">Win rate</div></div>
        <div class="stat-box"><div class="val">$${totalPnl}</div><div class="lbl">P&amp;L total</div></div>
        <div class="stat-box"><div class="val">${trades.length}</div><div class="lbl">Trades cerrados</div></div>
        <div class="stat-box"><div class="val">${Object.keys(user.open_positions || {}).length}</div><div class="lbl">Posiciones abiertas</div></div>
      </div>
      <div class="text-dim" style="font-size:12px;">Historial completo disponible en el <a href="autotrade.html">panel Auto Trade</a>.</div>
    `;
  } catch (e) {
    el.innerHTML = `<div class="text-dim">No se pudieron cargar las estadísticas.</div>`;
  }
}

// --- Inicialización ---
document.addEventListener("DOMContentLoaded", () => {
  renderChart();
  renderSignalPanel();
  renderWatchlist();
  syncSymbolControls();

  document.getElementById("symbol-select").addEventListener("change", (e) => setSymbol(e.target.value));
  document.querySelectorAll(".nav-symbol-btn").forEach((btn) => {
    btn.addEventListener("click", () => setSymbol(btn.dataset.symbol));
  });
  document.querySelectorAll(".tf-btn").forEach((btn) => {
    btn.addEventListener("click", () => setInterval_(btn.dataset.interval, btn));
  });
  document.querySelectorAll(".panel-tab").forEach((tab) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });
  document.getElementById("ai-send").addEventListener("click", sendAiQuestion);
  document.getElementById("ai-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendAiQuestion();
  });

  document.querySelectorAll(".broker-btn").forEach((btn) => {
    btn.addEventListener("click", () => setSelectedBroker(btn.dataset.broker));
  });
  loadBrokerSelector();
});

window.addEventListener("tradingai:signals", (e) => {
  latestSignals = e.detail || {};
  renderSignalPanel();
});
