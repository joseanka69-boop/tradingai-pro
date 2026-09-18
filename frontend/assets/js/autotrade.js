/**
 * Lógica del panel Auto Trade: registro de usuario, estado del trial,
 * posiciones abiertas en tiempo real, historial, stats y equity curve.
 */

const ALL_SYMBOLS = ["NQ", "MNQ", "AMD", "NVDA", "AAPL", "TSLA", "BTC", "ETH"];

function getUserId() {
  return localStorage.getItem("tradingai_user_id");
}

function setUserId(id) {
  localStorage.setItem("tradingai_user_id", id);
}

function daysRemaining(isoDate) {
  const diff = new Date(isoDate) - new Date();
  return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
}

async function fetchUser() {
  const userId = getUserId();
  if (!userId) return null;
  try {
    const res = await fetch(`/api/autotrade/user/${userId}`);
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    return null;
  }
}

let selectedBroker = localStorage.getItem("tradingai_broker") || "ibkr";

function renderRegisterForm() {
  document.getElementById("register-section").style.display = "block";
  document.getElementById("panel-section").style.display = "none";

  const symbolsEl = document.getElementById("symbols-checkboxes");
  symbolsEl.innerHTML = ALL_SYMBOLS.map((sym) => `
    <label style="display:inline-flex;align-items:center;gap:6px;margin:4px 10px 4px 0;">
      <input type="checkbox" value="${sym}" class="symbol-checkbox" /> ${sym}
    </label>
  `).join("");

  document.querySelectorAll(".broker-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.broker === selectedBroker);
  });
}

function handleBrokerSelect(broker) {
  selectedBroker = broker;
  localStorage.setItem("tradingai_broker", broker);
  document.querySelectorAll(".broker-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.broker === broker);
  });
}

async function handleRegister(e) {
  e.preventDefault();
  const phone = document.getElementById("phone-input").value.trim();
  const qty = parseInt(document.getElementById("qty-input").value, 10) || 1;
  const symbols = Array.from(document.querySelectorAll(".symbol-checkbox:checked")).map((cb) => cb.value);

  if (!phone || symbols.length === 0) {
    alert("Ingresa tu teléfono (formato +1XXXXXXXXXX) y selecciona al menos un símbolo.");
    return;
  }

  const res = await fetch("/api/autotrade/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone, plan: "trial", qty, symbols, broker: selectedBroker }),
  });
  const user = await res.json();
  setUserId(user.user_id);
  await refreshPanel();
}

function renderStatus(user) {
  const el = document.getElementById("status-box");
  const days = daysRemaining(user.trial_ends_at);
  const modeLabel = user.mode === "real" ? "REAL" : "PAPER (simulado)";
  el.innerHTML = `
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div>
          <div style="font-size:20px;font-weight:700;">${modeLabel}</div>
          <div class="text-dim" style="font-size:13px;">Plan: ${user.plan} · Broker: ${(user.broker || "ibkr").toUpperCase()}</div>
        </div>
        <div class="text-center">
          <div style="font-size:24px;font-weight:800;color:var(--accent-2);">${days}</div>
          <div class="text-dim" style="font-size:12px;">días de trial restantes</div>
        </div>
      </div>
    </div>
  `;
}

function renderOpenPositions(user) {
  const el = document.getElementById("open-positions");
  const symbols = Object.keys(user.open_positions || {});
  if (symbols.length === 0) {
    el.innerHTML = `<div class="text-dim">No tienes posiciones abiertas.</div>`;
    return;
  }
  el.innerHTML = symbols.map((sym) => {
    const p = user.open_positions[sym];
    const badgeClass = p.direction === "LONG" ? "badge-long" : "badge-short";
    return `
      <div class="card" style="margin-bottom:12px;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <div><strong>${sym}</strong> <span class="badge ${badgeClass}">${p.direction}</span></div>
          <button class="btn btn-ghost" onclick="closePosition('${sym}', ${p.entry_price})">Cerrar posición</button>
        </div>
        <div class="text-dim" style="font-size:13px;margin-top:8px;">
          Entrada: ${p.entry_price} · SL: ${p.stop_loss} · TP: ${p.take_profit} · Cantidad: ${p.qty}
        </div>
      </div>
    `;
  }).join("");
}

async function closePosition(symbol, currentPrice) {
  const userId = getUserId();
  await fetch("/api/autotrade/close", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, symbol, exit_price: currentPrice }),
  });
  await refreshPanel();
}

function renderHistory(user) {
  const el = document.getElementById("history-table");
  const trades = user.closed_trades || [];
  if (trades.length === 0) {
    el.innerHTML = `<div class="text-dim">Aún no hay trades cerrados.</div>`;
    return;
  }
  el.innerHTML = `
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr class="text-dim" style="text-align:left;border-bottom:1px solid var(--border);">
          <th style="padding:8px 4px;">Símbolo</th>
          <th>Dirección</th>
          <th>Entrada</th>
          <th>Salida</th>
          <th>P&amp;L</th>
          <th>Razón</th>
        </tr>
      </thead>
      <tbody>
        ${trades.slice().reverse().map((t) => `
          <tr style="border-bottom:1px solid var(--border);">
            <td style="padding:8px 4px;">${t.symbol}</td>
            <td>${t.direction}</td>
            <td>${t.entry_price}</td>
            <td>${t.exit_price}</td>
            <td style="color:${t.pnl >= 0 ? "var(--accent-2)" : "var(--danger)"}">$${t.pnl}</td>
            <td class="text-dim">${t.reason}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderStats(user) {
  const trades = user.closed_trades || [];
  const wins = trades.filter((t) => t.pnl > 0);
  const losses = trades.filter((t) => t.pnl <= 0);
  const winRate = trades.length ? ((wins.length / trades.length) * 100).toFixed(1) : "0.0";
  const grossProfit = wins.reduce((a, t) => a + t.pnl, 0);
  const grossLoss = Math.abs(losses.reduce((a, t) => a + t.pnl, 0));
  const profitFactor = grossLoss > 0 ? (grossProfit / grossLoss).toFixed(2) : "—";
  const totalPnl = trades.reduce((a, t) => a + t.pnl, 0).toFixed(2);

  document.getElementById("stats-grid").innerHTML = `
    <div class="stat-box"><div class="val">${winRate}%</div><div class="lbl">Win rate</div></div>
    <div class="stat-box"><div class="val">${profitFactor}</div><div class="lbl">Profit factor</div></div>
    <div class="stat-box"><div class="val">$${totalPnl}</div><div class="lbl">P&amp;L total</div></div>
    <div class="stat-box"><div class="val">${trades.length}</div><div class="lbl">Trades</div></div>
  `;

  drawEquityCurve(trades);
}

function drawEquityCurve(trades) {
  const canvas = document.getElementById("equity-canvas");
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);

  if (trades.length === 0) {
    ctx.fillStyle = "#8fa0bd";
    ctx.font = "13px sans-serif";
    ctx.fillText("Sin datos suficientes para la curva de equity", 10, h / 2);
    return;
  }

  let equity = 0;
  const points = trades.map((t) => (equity += t.pnl));
  const min = Math.min(0, ...points);
  const max = Math.max(0, ...points);
  const range = max - min || 1;

  ctx.strokeStyle = "#22c55e";
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((val, i) => {
    const x = (i / (points.length - 1 || 1)) * (w - 20) + 10;
    const y = h - 10 - ((val - min) / range) * (h - 20);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();
}

async function refreshPanel() {
  const user = await fetchUser();
  if (!user) {
    renderRegisterForm();
    return;
  }
  document.getElementById("register-section").style.display = "none";
  document.getElementById("panel-section").style.display = "block";
  renderStatus(user);
  renderOpenPositions(user);
  renderHistory(user);
  renderStats(user);
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("register-form").addEventListener("submit", handleRegister);
  document.querySelectorAll(".broker-btn").forEach((btn) => {
    btn.addEventListener("click", () => handleBrokerSelect(btn.dataset.broker));
  });
  refreshPanel();
  setInterval(refreshPanel, 15000);
});

window.addEventListener("tradingai:signals", () => {
  // Las posiciones abiertas dependen del precio actual; refrescamos el panel del usuario
  refreshPanel();
});
