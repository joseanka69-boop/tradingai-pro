/**
 * Conexión WebSocket compartida al backend de TradingAI Pro.
 * Emite el evento "tradingai:signals" en window con el payload recibido.
 */
(function () {
  function connect() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === "signals") {
          window.dispatchEvent(new CustomEvent("tradingai:signals", { detail: message.data }));
        }
      } catch (e) {
        console.warn("Mensaje WebSocket inválido", e);
      }
    };

    ws.onclose = () => {
      // Reintenta la conexión cada 5 segundos si se cae
      setTimeout(connect, 5000);
    };

    ws.onerror = () => ws.close();

    window.tradingaiSocket = ws;
  }

  connect();
})();
