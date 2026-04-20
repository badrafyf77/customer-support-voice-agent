export const DEFAULT_EXAM_SERVER_URL = process.env.NEXT_PUBLIC_EXAM_SERVER_URL || 'ws://162.243.59.37:8080';

export const ORAL_EXAM_SERVER_READY_TIMEOUT_MS = 60_000;
export const ORAL_EXAM_FINISH_TIMEOUT_MS = 30_000;
export const ORAL_EXAM_SOCKET_CONNECT_TIMEOUT_MS = 10_000;
export const ATTEMPT_EVALUATION_TRIGGER_MAX_ATTEMPTS = 3;
export const ATTEMPT_EVALUATION_TRIGGER_RETRY_DELAY_MS = 1_500;

export const ORAL_EXAM_AUDIO_CAPTURE_BATCH_SAMPLES = 2048;
export const ORAL_EXAM_AUDIO_CAPTURE_HEADER_BYTES = 8;

export const ORAL_EXAM_VIDEO_CONSTRAINTS = {
  width: { ideal: 1280 },
  height: { ideal: 720 },
  facingMode: 'user',
} as const;

export const ORAL_EXAM_AUDIO_CONSTRAINTS = {
  sampleRate: { ideal: 48_000 },
  channelCount: 1,
  echoCancellation: true,
  noiseSuppression: true,
} as const;
