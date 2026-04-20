'use client';

import { useCallback, useRef, useState } from 'react';
import {
  ORAL_EXAM_AUDIO_CAPTURE_BATCH_SAMPLES,
  ORAL_EXAM_AUDIO_CAPTURE_HEADER_BYTES,
  ORAL_EXAM_AUDIO_CONSTRAINTS,
} from '../constants';

const FRAME_BYTES = ORAL_EXAM_AUDIO_CAPTURE_BATCH_SAMPLES * 2;
const MESSAGE_BYTES = ORAL_EXAM_AUDIO_CAPTURE_HEADER_BYTES + FRAME_BYTES;

export function useAudioCapture(onAudioData: (data: ArrayBuffer) => void, getTtsPlayingState: () => boolean) {
  const [isCapturing, setIsCapturing] = useState(false);
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

    batchBufferRef.current = bufferPoolRef.current.pop() || new ArrayBuffer(MESSAGE_BYTES);
    batchViewRef.current = new DataView(batchBufferRef.current);
    batchInt16Ref.current = new Int16Array(batchBufferRef.current, ORAL_EXAM_AUDIO_CAPTURE_HEADER_BYTES);
    batchOffsetRef.current = 0;
  }, []);

  const flushBatch = useCallback(() => {
    if (!batchViewRef.current || !batchBufferRef.current) {
      return;
    }

    const timestamp = Date.now() & 0xffffffff;
    batchViewRef.current.setUint32(0, timestamp, false);
    batchViewRef.current.setUint32(4, getTtsPlayingState() ? 1 : 0, false);

    onAudioData(batchBufferRef.current);
    bufferPoolRef.current.push(batchBufferRef.current);
    batchBufferRef.current = null;
  }, [getTtsPlayingState, onAudioData]);

  const flushRemainder = useCallback(() => {
    if (batchOffsetRef.current === 0 || !batchInt16Ref.current) {
      return;
    }

    for (let index = batchOffsetRef.current; index < ORAL_EXAM_AUDIO_CAPTURE_BATCH_SAMPLES; index += 1) {
      batchInt16Ref.current[index] = 0;
    }

    flushBatch();
  }, [flushBatch]);

  const startCapture = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: ORAL_EXAM_AUDIO_CONSTRAINTS,
      });

      streamRef.current = stream;

      if (!audioContextRef.current) {
        audioContextRef.current = new AudioContext({ sampleRate: 48_000 });
      }

      await audioContextRef.current.audioWorklet.addModule('/static/pcmWorkletProcessor.js');

      workletNodeRef.current = new AudioWorkletNode(audioContextRef.current, 'pcm-worklet-processor');

      workletNodeRef.current.port.onmessage = ({ data }) => {
        const incoming = new Int16Array(data);
        let readOffset = 0;

        while (readOffset < incoming.length) {
          initializeBatch();

          const copyLength = Math.min(
            incoming.length - readOffset,
            ORAL_EXAM_AUDIO_CAPTURE_BATCH_SAMPLES - batchOffsetRef.current,
          );

          batchInt16Ref.current?.set(incoming.subarray(readOffset, readOffset + copyLength), batchOffsetRef.current);

          batchOffsetRef.current += copyLength;
          readOffset += copyLength;

          if (batchOffsetRef.current === ORAL_EXAM_AUDIO_CAPTURE_BATCH_SAMPLES) {
            flushBatch();
          }
        }
      };

      const source = audioContextRef.current.createMediaStreamSource(stream);
      source.connect(workletNodeRef.current);

      setIsCapturing(true);
    } catch (captureError) {
      console.error('Error starting audio capture:', captureError);
      throw captureError;
    }
  }, [flushBatch, initializeBatch]);

  const stopCapture = useCallback(() => {
    flushRemainder();

    workletNodeRef.current?.disconnect();
    workletNodeRef.current = null;

    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;

    void audioContextRef.current?.close();
    audioContextRef.current = null;

    setIsCapturing(false);
  }, [flushRemainder]);

  return {
    isCapturing,
    startCapture,
    stopCapture,
  };
}
