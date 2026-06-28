/**
 * WebSocket connection manager for real-time updates.
 * Manages reconnection, heartbeat, and message routing.
 */

import { toast } from './toast.js';

export function connectWS(role, handlers = {}) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = role === 'dispatcher'
    ? `${protocol}//${window.location.host}/ws/dispatcher/`
    : null;

  if (!wsUrl) return null;

  let ws = null;
  let reconnectTimer = null;
  let reconnectDelay = 1000;

  function connect() {
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      reconnectDelay = 1000;
    };

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        const handler = handlers[data.type];
        if (handler) handler(data);
      } catch { /* ignore malformed messages */ }
    };

    ws.onclose = () => {
      reconnectTimer = setTimeout(() => {
        reconnectDelay = Math.min(reconnectDelay * 2, 30000);
        connect();
      }, reconnectDelay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }

  connect();

  return {
    close: () => {
      clearTimeout(reconnectTimer);
      if (ws) ws.close();
    },
  };
}
