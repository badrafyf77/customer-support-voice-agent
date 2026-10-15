// Paste in DevTools before Connect. Save with copy(JSON.stringify(voiceTrace.events)).
// No transcript text, audio, credentials, or identifiers are recorded.
(() => {
  if (window.voiceTrace) throw new Error("Restore the existing voiceTrace before reinstalling.");
  const events = [];
  const audioContexts = [];
  const record = (event, detail = {}) => {
    if (events.length >= 100000) return; // Bound memory during long sessions.
    events.push({ event, browser_ms: performance.now(), ...detail });
  };
  const OriginalWebSocket = window.WebSocket;
  const OriginalAudioWorkletNode = window.AudioWorkletNode;
  window.WebSocket = class extends OriginalWebSocket {
    constructor(...args) {
      super(...args);
      this.addEventListener("message", ({ data }) => {
        if (typeof data !== "string") return;
        try {
          const message = JSON.parse(data);
          record("server:" + message.type, {
            ...(message.type === "status" ? { status: message.status } : {}),
            ...(Number.isSafeInteger(message.generation_id) ? { generation_id: message.generation_id } : {}),
          });
        } catch {}
      });
      this.addEventListener("open", () => record("socket:open"));
      this.addEventListener("close", () => record("socket:close"));
    }
    send(data) {
      if (typeof data === "string") {
        try { record("client:" + JSON.parse(data).type); } catch {}
      }
      return super.send(data);
    }
  };
  window.AudioWorkletNode = class extends OriginalAudioWorkletNode {
    constructor(context, name, ...args) {
      super(context, name, ...args);
      if (name === "tts-playback-processor") {
        audioContexts.push({ sample_rate: context.sampleRate,
          base_latency_seconds: context.baseLatency,
          output_latency_seconds: context.outputLatency });
        this.port.addEventListener("message", ({ data }) =>
          record("playback:" + data.type));
        this.port.start();
      }
    }
  };
  let controls;
  window.voiceTrace = {
    events,
    mark: (event) => record("mark:" + event),
    download: () => {
      const url = URL.createObjectURL(new Blob([JSON.stringify({
        events, audio_contexts: audioContexts, truncated: events.length >= 100000,
        physical_audio_measurement: false,
      }, null, 2)], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url; link.download = "browser-trace.json"; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
    controls: () => {
      if (controls) return;
      controls = document.createElement("div");
      controls.style.cssText = "position:fixed;bottom:8px;right:8px;z-index:99999;background:#fff;color:#111;padding:8px;border:2px solid #555;display:flex;gap:8px";
      for (const [label, action] of [
        ["Mark utterance end", () => record("mark:utterance_end")],
        ["Mark interruption start", () => record("mark:interrupt_start")],
        ["Save timing trace", () => window.voiceTrace.download()],
      ]) {
        const button = document.createElement("button");
        button.textContent = label; button.onclick = action; controls.appendChild(button);
      }
      document.body.appendChild(controls);
    },
    restore: () => {
      window.WebSocket = OriginalWebSocket;
      window.AudioWorkletNode = OriginalAudioWorkletNode;
      controls?.remove();
      delete window.voiceTrace;
    },
  };
  record("trace:installed");
})();
