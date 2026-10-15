"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { PlaybackGeneration } from "@/lib/generation";

const DEFAULT_VOICE_SERVER_URL =
  process.env.NEXT_PUBLIC_VOICE_SERVER_URL || "http://localhost:8080";
const SERVER_READY_TIMEOUT_MS = 60_000;
const SOCKET_CONNECT_TIMEOUT_MS = 10_000;
const AUDIO_BATCH_SAMPLES = 2048;
const AUDIO_HEADER_BYTES = 8;
const AUDIO_MESSAGE_BYTES = AUDIO_HEADER_BYTES + AUDIO_BATCH_SAMPLES * 2;

type TranscriptMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  type: "partial" | "final";
  generationId?: number;
  finishComplete?: boolean;
  success?: boolean;
  error?: string;
};

type WebSocketPayload = {
  type: string;
  generation_id?: number;
  status?: string;
  message?: string;
  content?: string;
  success?: boolean;
  error?: string;
};

function normalizeServerUrl(value: string) {
  const trimmedValue = value.trim() || DEFAULT_VOICE_SERVER_URL;
  return /^(https?|wss?):\/\//i.test(trimmedValue)
    ? trimmedValue
    : `http://${trimmedValue}`;
}

function buildWebSocketUrl(serverUrl: string) {
  const baseUrl = new URL(normalizeServerUrl(serverUrl));

  if (baseUrl.protocol === "http:") {
    baseUrl.protocol = "ws:";
  } else if (baseUrl.protocol === "https:") {
    baseUrl.protocol = "wss:";
  }

  baseUrl.pathname = "/ws";
  baseUrl.search = "";
  baseUrl.hash = "";
  return baseUrl.toString();
}

function base64ToInt16Array(value: string) {
  const rawValue = atob(value);
  const bytes = new Uint8Array(rawValue.length);

  for (let index = 0; index < rawValue.length; index += 1) {
    bytes[index] = rawValue.charCodeAt(index);
  }

  return new Int16Array(bytes.buffer);
}

function createTranscriptMessage(
  role: TranscriptMessage["role"],
  content: string,
  type: TranscriptMessage["type"],
): TranscriptMessage {
  return {
    id: `${role}-${type}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
    type,
  };
}

function upsertUserMessage(
  previousMessages: TranscriptMessage[],
  content: string,
  type: TranscriptMessage["type"],
) {
  if (!content.trim()) {
    return previousMessages;
  }

  const lastUserIndex = previousMessages.findLastIndex(
    (message) => message.role === "user",
  );
  const nextMessage = createTranscriptMessage("user", content, type);

  if (
    lastUserIndex === -1 ||
    previousMessages[lastUserIndex].type !== "partial"
  ) {
    return [...previousMessages, nextMessage];
  }

  const updatedMessages = [...previousMessages];
  updatedMessages[lastUserIndex] = nextMessage;
  return updatedMessages;
}

function waitForReady(isReadyRef: { current: boolean }, cancelled: () => boolean, failure: () => string) {
  return new Promise<void>((resolve, reject) => {
    const startedAt = Date.now();

    const check = () => {
      if (failure()) { reject(new Error(failure())); return; }
      if (cancelled()) { reject(new Error("Connection cancelled.")); return; }
      if (isReadyRef.current) {
        resolve();
        return;
      }

      if (Date.now() - startedAt >= SERVER_READY_TIMEOUT_MS) {
        reject(
          new Error("The voice agent server did not become ready in time."),
        );
        return;
      }

      window.setTimeout(check, 100);
    };

    check();
  });
}

function useVoiceSocket(serverUrl: string) {
  const [isConnected, setIsConnected] = useState(false);
  const [isReady, setIsReady] = useState(false);
  const [serverStatus, setServerStatus] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [messages, setMessages] = useState<TranscriptMessage[]>([]);
  const [isTtsPlaying, setIsTtsPlaying] = useState(false);
  const [connectionError, setConnectionError] = useState("");
  const connectionEpochRef = useRef(0);
  const generationRef = useRef(new PlaybackGeneration());

  const socketRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const ttsWorkletNodeRef = useRef<AudioWorkletNode | null>(null);
  const connectionPromiseRef = useRef<Promise<void> | null>(null);

  const initializeAudioPlayback = useCallback(async () => {
    if (audioContextRef.current && ttsWorkletNodeRef.current) {
      return;
    }

    const epoch = connectionEpochRef.current;
    const audioContext = new AudioContext({ sampleRate: 24_000 });
    audioContextRef.current = audioContext;
    await audioContext.audioWorklet.addModule(
      "/static/ttsPlaybackProcessor.js",
    );
    if (connectionEpochRef.current !== epoch) { await audioContext.close().catch(() => {}); throw new Error("Connection cancelled."); }
    await audioContext.resume();
    if (connectionEpochRef.current !== epoch) { await audioContext.close().catch(() => {}); throw new Error("Connection cancelled."); }

    const ttsWorkletNode = new AudioWorkletNode(
      audioContext,
      "tts-playback-processor",
    );
    ttsWorkletNode.port.onmessage = ({ data }) => {
      if (ttsWorkletNodeRef.current !== ttsWorkletNode) return;
      if (data.type === "ttsPlaybackStarted") {
        setIsTtsPlaying(true);
        if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify({ type: "tts_start" }));
      }

      if (data.type === "ttsPlaybackStopped") {
        setIsTtsPlaying(false);
        if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify({ type: "tts_stop" }));
      }
    };

    ttsWorkletNode.connect(audioContext.destination);
    audioContextRef.current = audioContext;
    ttsWorkletNodeRef.current = ttsWorkletNode;
  }, []);

  const disconnect = useCallback(() => {
    connectionEpochRef.current += 1;
    connectionPromiseRef.current = null;

    socketRef.current?.close();
    socketRef.current = null;

    ttsWorkletNodeRef.current?.port.postMessage({ type: "clear" });
    ttsWorkletNodeRef.current?.disconnect();
    ttsWorkletNodeRef.current = null;

    void audioContextRef.current?.close();
    audioContextRef.current = null;

    setIsConnected(false);
    setIsReady(false);
    setServerStatus("");
    setStatusMessage("");
    setIsTtsPlaying(false);
  }, []);

  const handleJsonMessage = useCallback((payload: WebSocketPayload) => {
    if (["tts_chunk", "assistant_partial", "partial_assistant_answer", "assistant_sentence"].includes(payload.type)
        && !generationRef.current.accept(payload.generation_id)) return;
    switch (payload.type) {
      case "status":
        setServerStatus(payload.status || "");
        setStatusMessage(payload.message || "");
        setIsReady(payload.status === "ready");
        if (payload.status === "error" || payload.status === "busy") {
          setConnectionError(payload.message || "The voice service is unavailable.");
          generationRef.current.stop();
          ttsWorkletNodeRef.current?.port.postMessage({ type: "clear" });
          setIsTtsPlaying(false);
        }
        break;

      case "partial_user_request":
        setMessages((previousMessages) =>
          payload.content
            ? upsertUserMessage(previousMessages, payload.content, "partial")
            : previousMessages,
        );
        break;

      case "final_user_request":
        setMessages((previousMessages) =>
          payload.content
            ? upsertUserMessage(previousMessages, payload.content, "final")
            : previousMessages,
        );
        break;

      case "assistant_partial":
      case "partial_assistant_answer":
      case "assistant_sentence":
        setMessages((previousMessages) => {
          if (!payload.content?.trim()) {
            return previousMessages;
          }

          const lastAssistantIndex = previousMessages.findLastIndex(
            (message) =>
              message.role === "assistant" && message.type === "partial" &&
              (payload.generation_id === undefined || message.generationId === payload.generation_id),
          );

          if (lastAssistantIndex === -1) {
            return [
              ...previousMessages,
              { ...createTranscriptMessage("assistant", payload.content, "partial"), generationId: payload.generation_id },
            ];
          }

          const updatedMessages = [...previousMessages];
          const previousContent = updatedMessages[lastAssistantIndex].content;
          updatedMessages[lastAssistantIndex] = {
            ...updatedMessages[lastAssistantIndex],
            content:
              payload.type === "assistant_sentence" &&
              !previousContent.includes(payload.content)
                ? `${previousContent}${payload.content}`
                : payload.content,
          };

          return updatedMessages;
        });
        break;

      case "final_assistant_answer":
        setMessages((previousMessages) => {
          if (!payload.content?.trim()) {
            return previousMessages;
          }

          const lastAssistantIndex = previousMessages.findLastIndex(
            (message) =>
              message.role === "assistant" && message.type === "partial" &&
              (payload.generation_id === undefined || message.generationId === payload.generation_id),
          );

          if (lastAssistantIndex === -1) {
            return [
              ...previousMessages,
              { ...createTranscriptMessage("assistant", payload.content, "final"), generationId: payload.generation_id },
            ];
          }

          const updatedMessages = [...previousMessages];
          updatedMessages[lastAssistantIndex] = {
            ...updatedMessages[lastAssistantIndex],
            content: payload.content,
            type: "final",
          };
          return updatedMessages;
        });
        break;

      case "tts_chunk":
        if (ttsWorkletNodeRef.current && payload.content) {
          ttsWorkletNodeRef.current.port.postMessage(
            base64ToInt16Array(payload.content),
          );
        }
        break;

      case "tts_interruption":
      case "stop_tts":
        if (!generationRef.current.stop(payload.generation_id)) break;
        ttsWorkletNodeRef.current?.port.postMessage({ type: "clear" });
        setIsTtsPlaying(false);
        break;

      case "finish_complete":
        setMessages((previousMessages) => [
          ...previousMessages,
          {
            ...createTranscriptMessage(
              "assistant",
              payload.error || "Voice chat ended.",
              "final",
            ),
            finishComplete: true,
            success: payload.success,
            error: payload.error,
          },
        ]);
        break;

      default:
        break;
    }
  }, []);

  const connect = useCallback(async () => {
    if (socketRef.current?.readyState === WebSocket.OPEN) return;
    if (connectionPromiseRef.current) return connectionPromiseRef.current;
    const epoch = ++connectionEpochRef.current;
    setConnectionError("");
    setMessages([]);
    generationRef.current = new PlaybackGeneration();
    const pending = (async () => {
      await initializeAudioPlayback();
      if (connectionEpochRef.current !== epoch) throw new Error("Connection cancelled.");
      await new Promise<void>((resolve, reject) => {
        const socket = new WebSocket(buildWebSocketUrl(serverUrl));
        socketRef.current = socket;
        let settled = false;
        const current = () => socketRef.current === socket && connectionEpochRef.current === epoch;
        const finish = (error?: Error) => {
          if (settled) return;
          settled = true;
          window.clearTimeout(timeoutId);
          if (error) reject(error); else resolve();
        };
        const timeoutId = window.setTimeout(() => {
          finish(new Error("Timed out while connecting to the voice chat server."));
          socket.close();
        }, SOCKET_CONNECT_TIMEOUT_MS);
        socket.onopen = () => {
          if (!current()) { socket.close(); finish(new Error("Connection cancelled.")); return; }
          setIsConnected(true); setIsReady(false); setStatusMessage("Connecting..."); finish();
        };
        socket.onmessage = (event) => {
          if (!current() || typeof event.data !== "string") return;
          try { handleJsonMessage(JSON.parse(event.data) as WebSocketPayload); }
          catch (error) { console.error("Invalid voice-agent message:", error); }
        };
        socket.onclose = () => {
          finish(new Error("The voice chat server closed the connection."));
          if (!current()) return;
          socketRef.current = null;
          generationRef.current.stop();
          ttsWorkletNodeRef.current?.port.postMessage({ type: "clear" });
          setIsConnected(false); setIsReady(false); setIsTtsPlaying(false);
          setStatusMessage("Disconnected");
          setConnectionError(previous => previous || "The voice connection closed. Start again to reconnect.");
        };
        socket.onerror = () => {
          if (current()) setConnectionError("Unable to connect to the voice chat server.");
          finish(new Error("Unable to connect to the voice chat server."));
        };
      });
    })();
    connectionPromiseRef.current = pending;
    try { await pending; }
    finally { if (connectionPromiseRef.current === pending) connectionPromiseRef.current = null; }
  }, [handleJsonMessage, initializeAudioPlayback, serverUrl]);

  const sendAudioData = useCallback((audioBuffer: ArrayBuffer) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(audioBuffer);
    }
  }, []);

  const sendMessage = useCallback((message: Record<string, unknown>) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(message));
    }
  }, []);

  const clearHistory = useCallback(() => {
    setMessages([]);
    generationRef.current.stop();
    ttsWorkletNodeRef.current?.port.postMessage({ type: "clear" });
    setIsTtsPlaying(false);
    sendMessage({ type: "clear_history" });
  }, [sendMessage]);

  const stopTts = useCallback(() => {
    ttsWorkletNodeRef.current?.port.postMessage({ type: "clear" });
    setIsTtsPlaying(false);
  }, []);

  useEffect(() => disconnect, [disconnect]);

  return {
    connectionError,
    isConnected,
    isReady,
    serverStatus,
    statusMessage,
    messages,
    connect,
    disconnect,
    clearHistory,
    sendAudioData,
    stopTts,
    isTtsPlaying,
  };
}

function useAudioCapture(
  onAudioData: (data: ArrayBuffer) => void,
  getTtsPlayingState: () => boolean,
) {
  const [isCapturing, setIsCapturing] = useState(false);
  const captureEpochRef = useRef(0);
  const audioContextRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const batchBufferRef = useRef<ArrayBuffer | null>(null);
  const batchViewRef = useRef<DataView | null>(null);
  const batchInt16Ref = useRef<Int16Array | null>(null);
  const batchOffsetRef = useRef(0);
  const bufferPoolRef = useRef<ArrayBuffer[]>([]);

  const initializeBatch = useCallback(() => {
    if (batchBufferRef.current) {
      return;
    }

    batchBufferRef.current =
      bufferPoolRef.current.pop() || new ArrayBuffer(AUDIO_MESSAGE_BYTES);
    batchViewRef.current = new DataView(batchBufferRef.current);
    batchInt16Ref.current = new Int16Array(
      batchBufferRef.current,
      AUDIO_HEADER_BYTES,
    );
    batchOffsetRef.current = 0;
  }, []);

  const flushBatch = useCallback(() => {
    if (!batchViewRef.current || !batchBufferRef.current) {
      return;
    }

    const buffer = batchBufferRef.current;
    batchViewRef.current.setUint32(0, Date.now() & 0xffffffff, false);
    batchViewRef.current.setUint32(4, getTtsPlayingState() ? 1 : 0, false);
    onAudioData(buffer);

    bufferPoolRef.current.push(buffer);
    batchBufferRef.current = null;
    batchViewRef.current = null;
    batchInt16Ref.current = null;
    batchOffsetRef.current = 0;
  }, [getTtsPlayingState, onAudioData]);

  const flushRemainder = useCallback(() => {
    if (batchOffsetRef.current === 0 || !batchInt16Ref.current) {
      return;
    }

    for (
      let index = batchOffsetRef.current;
      index < AUDIO_BATCH_SAMPLES;
      index += 1
    ) {
      batchInt16Ref.current[index] = 0;
    }

    flushBatch();
  }, [flushBatch]);

  const startCapture = useCallback(async () => {
    const epoch = ++captureEpochRef.current;
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        sampleRate: { ideal: 48_000 },
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });

    if (epoch !== captureEpochRef.current) { stream.getTracks().forEach(track => track.stop()); return false; }
    streamRef.current = stream;

    const audioContext = new AudioContext({ sampleRate: 48_000 });
    audioContextRef.current = audioContext;
    await audioContext.audioWorklet.addModule("/static/pcmWorkletProcessor.js");
    if (epoch !== captureEpochRef.current) { await audioContext.close().catch(() => {}); return false; }
    await audioContext.resume();
    if (epoch !== captureEpochRef.current) { await audioContext.close().catch(() => {}); return false; }

    const workletNode = new AudioWorkletNode(
      audioContext,
      "pcm-worklet-processor",
    );
    workletNode.port.onmessage = ({ data }) => {
      if (epoch !== captureEpochRef.current) return;
      const incoming = new Int16Array(data);
      let readOffset = 0;

      while (readOffset < incoming.length) {
        initializeBatch();

        const copyLength = Math.min(
          incoming.length - readOffset,
          AUDIO_BATCH_SAMPLES - batchOffsetRef.current,
        );
        batchInt16Ref.current?.set(
          incoming.subarray(readOffset, readOffset + copyLength),
          batchOffsetRef.current,
        );

        batchOffsetRef.current += copyLength;
        readOffset += copyLength;

        if (batchOffsetRef.current === AUDIO_BATCH_SAMPLES) {
          flushBatch();
        }
      }
    };

    audioContext.createMediaStreamSource(stream).connect(workletNode);
    audioContextRef.current = audioContext;
    workletNodeRef.current = workletNode;
    setIsCapturing(true);
    return true;
  }, [flushBatch, initializeBatch]);

  const stopCapture = useCallback(() => {
    captureEpochRef.current += 1;
    flushRemainder();

    workletNodeRef.current?.disconnect();
    workletNodeRef.current = null;

    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;

    void audioContextRef.current?.close();
    audioContextRef.current = null;

    setIsCapturing(false);
  }, [flushRemainder]);

  useEffect(() => stopCapture, [stopCapture]);

  return {
    isCapturing,
    startCapture,
    stopCapture,
  };
}

function transcriptLabel(message: TranscriptMessage) {
  return message.role === "assistant" ? "Assistant" : "You";
}

export default function Home() {
  const [serverUrl, setServerUrl] = useState(DEFAULT_VOICE_SERVER_URL);
  const [isStarting, setIsStarting] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const isReadyRef = useRef(false);
  const startEpochRef = useRef(0);
  const connectionErrorRef = useRef("");
  const isTtsPlayingRef = useRef(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setServerUrl(params.get("server") || DEFAULT_VOICE_SERVER_URL);
  }, []);

  const {
    connectionError,
    isConnected,
    isReady,
    serverStatus,
    statusMessage,
    messages,
    connect,
    disconnect,
    clearHistory,
    sendAudioData,
    stopTts,
    isTtsPlaying,
  } = useVoiceSocket(serverUrl);

  const getTtsPlayingState = useCallback(() => isTtsPlayingRef.current, []);
  const { startCapture, stopCapture } = useAudioCapture(sendAudioData, getTtsPlayingState);

  useEffect(() => {
    connectionErrorRef.current = connectionError;
    if (!isConnected) { stopCapture(); setIsRecording(false); }
    if (connectionError) { stopCapture(); setIsRecording(false); setErrorMessage(connectionError); }
  }, [isConnected, connectionError, stopCapture]);

  useEffect(() => {
    isReadyRef.current = isReady;
  }, [isReady]);

  useEffect(() => {
    isTtsPlayingRef.current = isTtsPlaying;
  }, [isTtsPlaying]);

  useEffect(() => {
    const finishMessage = [...messages]
      .reverse()
      .find((message) => message.finishComplete);
    if (!finishMessage) {
      return;
    }

    stopCapture();
    setIsRecording(false);

    if (!finishMessage.success) {
      setErrorMessage(
        finishMessage.error || "The voice chat could not be ended cleanly.",
      );
    }
  }, [messages, stopCapture]);

  const stopSession = useCallback(() => {
    startEpochRef.current += 1;
    stopTts();
    stopCapture();
    disconnect();
    setIsRecording(false);
    setIsStarting(false);
  }, [disconnect, stopCapture, stopTts]);

  const startSession = useCallback(async () => {
    const epoch = ++startEpochRef.current;
    isReadyRef.current = false;
    connectionErrorRef.current = "";
    setErrorMessage("");
    setIsStarting(true);

    try {
      await connect();
      if (epoch !== startEpochRef.current) return;
      await waitForReady(isReadyRef, () => epoch !== startEpochRef.current, () => connectionErrorRef.current);
      if (epoch !== startEpochRef.current) return;
      const started = await startCapture();
      if (epoch === startEpochRef.current && started) setIsRecording(true);
    } catch (error) {
      if (epoch !== startEpochRef.current) return;
      stopSession();
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Could not start the voice agent.",
      );
    } finally {
      if (epoch === startEpochRef.current) setIsStarting(false);
    }
  }, [connect, startCapture, stopSession]);

  const resetTranscript = useCallback(() => {
    clearHistory();
    setErrorMessage("");
  }, [clearHistory]);

  const canStart = !isConnected && !isStarting;
  const currentStatus =
    statusMessage || (isConnected ? "Connected" : "Disconnected");
  const activityStatus = isTtsPlaying
    ? "Speaking"
    : isRecording
      ? "Listening"
      : "Idle";

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Voice Agent</p>
          <h1>Voice Chat</h1>
        </div>
        <div className="status-pill">
          <span
            className={`status-dot ${isReady ? "ready" : isConnected ? "connecting" : ""}`}
          />
          <span>{currentStatus}</span>
        </div>
      </header>

      <section className="workspace">
        <aside className="controls-panel">
          <label>
            <span>Server</span>
            <input
              value={serverUrl}
              onChange={(event) => setServerUrl(event.target.value)}
              disabled={isConnected}
            />
          </label>

          {errorMessage ? (
            <div className="error-box" role="alert">{errorMessage}</div>
          ) : null}

          <div className="button-grid">
            <button
              type="button"
              className="primary-button"
              onClick={startSession}
              disabled={!canStart}
            >
              {isStarting ? "Starting..." : "Start"}
            </button>
            <button type="button" onClick={stopSession} disabled={!isConnected && !isStarting}>
              Stop
            </button>
            <button
              type="button"
              className="reset-button"
              onClick={resetTranscript}
            >
              Reset Transcript
            </button>
          </div>

          <div className="mic-status">
            <span className={`mic-dot ${isRecording ? "active" : ""}`} />
            <span>
              {isRecording
                ? "Microphone is streaming."
                : serverStatus || "Ready to connect."}
            </span>
          </div>
        </aside>

        <section className="transcript-panel">
          <div className="transcript-header">
            <h2>Transcript</h2>
            <span>{activityStatus}</span>
          </div>

          <div className="transcript">
            {messages.length === 0 ? (
              <p className="empty-state">Conversation will appear here.</p>
            ) : (
              messages.map((message) => (
                <article key={message.id} className={`message ${message.role}`}>
                  <div className="message-label">
                    {transcriptLabel(message)}
                  </div>
                  <p className="message-content" dir="auto">{message.content}</p>
                </article>
              ))
            )}
          </div>
        </section>
      </section>
    </main>
  );
}
