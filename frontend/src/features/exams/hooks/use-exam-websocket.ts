'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ORAL_EXAM_SOCKET_CONNECT_TIMEOUT_MS } from '../constants';
import type { ExamTranscriptMessage, ExamWebSocketMessage } from '../types';

interface WebSocketOptions {
  userId?: string;
  examId?: string;
  attemptId?: string;
}

function base64ToInt16Array(base64Value: string) {
  const rawValue = atob(base64Value);
  const buffer = new ArrayBuffer(rawValue.length);
  const view = new Uint8Array(buffer);

  for (let index = 0; index < rawValue.length; index += 1) {
    view[index] = rawValue.charCodeAt(index);
  }

  return new Int16Array(buffer);
}

function buildWebSocketUrl(serverUrl: string, options?: WebSocketOptions) {
  const url = new URL('/ws', serverUrl.replace(/^http/, 'ws'));

  if (options?.userId) {
    url.searchParams.set('user_id', options.userId);
  }

  if (options?.examId) {
    url.searchParams.set('exam_id', options.examId);
  }

  if (options?.attemptId) {
    url.searchParams.set('attempt_id', options.attemptId);
  }

  return url.toString();
}

function createTranscriptMessage(
  role: 'user' | 'assistant',
  content: string,
  type: ExamTranscriptMessage['type'],
): ExamTranscriptMessage {
  return {
    id: `${role}-${type}-${Date.now()}`,
    role,
    content,
    type,
    timestamp: Date.now(),
  };
}

function upsertUserMessage(
  previousMessages: ExamTranscriptMessage[],
  content: string,
  type: ExamTranscriptMessage['type'],
) {
  if (!content.trim()) {
    return previousMessages;
  }

  const lastUserIndex = previousMessages.findLastIndex((message) => message.role === 'user');
  const nextMessage = createTranscriptMessage('user', content, type);

  if (lastUserIndex === -1) {
    return [...previousMessages, nextMessage];
  }

  const lastUserMessage = previousMessages[lastUserIndex];
  if (lastUserMessage.type === 'partial') {
    const updatedMessages = [...previousMessages];
    updatedMessages[lastUserIndex] = {
      ...lastUserMessage,
      content,
      type,
      timestamp: nextMessage.timestamp,
    };
    return updatedMessages;
  }

  return [...previousMessages, nextMessage];
}

export function useExamWebSocket(serverUrl: string, options?: WebSocketOptions) {
  const [isConnected, setIsConnected] = useState(false);
  const [isReady, setIsReady] = useState(false);
  const [serverStatus, setServerStatus] = useState('');
  const [statusMessage, setStatusMessage] = useState('');
  const [messages, setMessages] = useState<ExamTranscriptMessage[]>([]);
  const [isTtsPlaying, setIsTtsPlaying] = useState(false);

  const socketRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const ttsWorkletNodeRef = useRef<AudioWorkletNode | null>(null);
  const connectionPromiseRef = useRef<Promise<void> | null>(null);

  const initializeAudioPlayback = useCallback(async () => {
    if (audioContextRef.current && ttsWorkletNodeRef.current) {
      return;
    }

    audioContextRef.current = new AudioContext({ sampleRate: 24_000 });
    await audioContextRef.current.audioWorklet.addModule('/static/ttsPlaybackProcessor.js');

    ttsWorkletNodeRef.current = new AudioWorkletNode(audioContextRef.current, 'tts-playback-processor');

    ttsWorkletNodeRef.current.port.onmessage = ({ data }) => {
      if (data.type === 'ttsPlaybackStarted') {
        setIsTtsPlaying(true);
        socketRef.current?.send(JSON.stringify({ type: 'tts_start' }));
      }

      if (data.type === 'ttsPlaybackStopped') {
        setIsTtsPlaying(false);
        socketRef.current?.send(JSON.stringify({ type: 'tts_stop' }));
      }
    };

    ttsWorkletNodeRef.current.connect(audioContextRef.current.destination);
  }, []);

  const disconnect = useCallback(() => {
    connectionPromiseRef.current = null;

    socketRef.current?.close();
    socketRef.current = null;

    ttsWorkletNodeRef.current?.disconnect();
    ttsWorkletNodeRef.current = null;

    void audioContextRef.current?.close();
    audioContextRef.current = null;

    setIsConnected(false);
    setIsReady(false);
    setServerStatus('');
    setIsTtsPlaying(false);
    setStatusMessage('');
  }, []);

  const handleJsonMessage = useCallback((payload: ExamWebSocketMessage) => {
    if (payload.type !== 'tts_chunk') {
      console.log('Exam WebSocket message:', payload);
    }

    switch (payload.type) {
      case 'status':
        setServerStatus(payload.status || '');
        setStatusMessage(payload.message || '');
        setIsReady(payload.status === 'ready');
        break;

      case 'partial_user_request':
        setMessages((previousMessages) =>
          payload.content ? upsertUserMessage(previousMessages, payload.content, 'partial') : previousMessages,
        );
        break;

      case 'final_user_request':
        setMessages((previousMessages) =>
          payload.content ? upsertUserMessage(previousMessages, payload.content, 'final') : previousMessages,
        );
        break;

      case 'assistant_partial':
      case 'partial_assistant_answer':
      case 'assistant_sentence':
        setMessages((previousMessages) => {
          if (!payload.content?.trim()) {
            return previousMessages;
          }

          const lastAssistantIndex = previousMessages.findLastIndex(
            (message) => message.role === 'assistant' && message.type === 'partial',
          );

          if (lastAssistantIndex === -1) {
            return [...previousMessages, createTranscriptMessage('assistant', payload.content, 'partial')];
          }

          const updatedMessages = [...previousMessages];
          updatedMessages[lastAssistantIndex] = {
            ...updatedMessages[lastAssistantIndex],
            content:
              payload.type === 'assistant_sentence' &&
              !updatedMessages[lastAssistantIndex].content.includes(payload.content)
                ? `${updatedMessages[lastAssistantIndex].content} ${payload.content}`.trim()
                : payload.content,
          };

          return updatedMessages;
        });
        break;

      case 'final_assistant_answer':
        setMessages((previousMessages) => {
          if (!payload.content?.trim()) {
            return previousMessages;
          }

          const lastAssistantIndex = previousMessages.findLastIndex(
            (message) => message.role === 'assistant' && message.type === 'partial',
          );

          if (lastAssistantIndex === -1) {
            return [...previousMessages, createTranscriptMessage('assistant', payload.content, 'final')];
          }

          const updatedMessages = [...previousMessages];
          updatedMessages[lastAssistantIndex] = {
            ...updatedMessages[lastAssistantIndex],
            content: payload.content,
            type: 'final',
          };

          return updatedMessages;
        });
        break;

      case 'tts_chunk':
        if (ttsWorkletNodeRef.current && payload.content) {
          ttsWorkletNodeRef.current.port.postMessage(base64ToInt16Array(payload.content));
        }
        break;

      case 'tts_interruption':
      case 'stop_tts':
        ttsWorkletNodeRef.current?.port.postMessage({ type: 'clear' });
        setIsTtsPlaying(false);
        break;

      case 'finish_complete':
        setMessages((previousMessages) => [
          ...previousMessages,
          {
            id: `finish-complete-${Date.now()}`,
            role: 'assistant',
            content: payload.error || 'Oral exam completed.',
            type: 'final',
            timestamp: Date.now(),
            finishComplete: true,
            success: payload.success,
            attemptId: payload.attempt_id,
            examId: payload.exam_id,
            overallScore: payload.overall_score,
            error: payload.error,
          },
        ]);
        break;

      default:
        break;
    }
  }, []);

  const connect = useCallback(async () => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    if (connectionPromiseRef.current) {
      return connectionPromiseRef.current;
    }

    await initializeAudioPlayback();

    connectionPromiseRef.current = new Promise<void>((resolve, reject) => {
      let settled = false;
      const socket = new WebSocket(buildWebSocketUrl(serverUrl, options));

      const cleanup = () => {
        connectionPromiseRef.current = null;
        window.clearTimeout(timeoutId);
      };

      const resolveOnce = () => {
        if (settled) {
          return;
        }

        settled = true;
        cleanup();
        resolve();
      };

      const rejectOnce = (error: Error) => {
        if (settled) {
          return;
        }

        settled = true;
        cleanup();
        reject(error);
      };

      const timeoutId = window.setTimeout(() => {
        socket.close();
        rejectOnce(new Error('Timed out while connecting to the oral exam server.'));
      }, ORAL_EXAM_SOCKET_CONNECT_TIMEOUT_MS);

      socket.onopen = () => {
        setIsConnected(true);
        setIsReady(false);
        setStatusMessage('Connecting...');
        resolveOnce();
      };

      socket.onmessage = (event) => {
        if (typeof event.data !== 'string') {
          return;
        }

        try {
          handleJsonMessage(JSON.parse(event.data) as ExamWebSocketMessage);
        } catch (parseError) {
          console.error('Error parsing oral exam socket message:', parseError);
        }
      };

      socket.onclose = () => {
        setIsConnected(false);
        setIsReady(false);
        setStatusMessage('');

        if (!settled) {
          rejectOnce(new Error('The oral exam server closed the connection.'));
        }
      };

      socket.onerror = () => {
        setIsConnected(false);
        rejectOnce(new Error('Unable to connect to the oral exam server.'));
      };

      socketRef.current = socket;
    });

    return connectionPromiseRef.current;
  }, [handleJsonMessage, initializeAudioPlayback, options, serverUrl]);

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
    sendMessage({ type: 'clear_history' });
  }, [sendMessage]);

  const stopTts = useCallback(() => {
    ttsWorkletNodeRef.current?.port.postMessage({ type: 'clear' });
    setIsTtsPlaying(false);
  }, []);

  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    isConnected,
    isReady,
    serverStatus,
    statusMessage,
    messages,
    connect,
    disconnect,
    clearHistory,
    sendAudioData,
    sendMessage,
    stopTts,
    isTtsPlaying,
  };
}
