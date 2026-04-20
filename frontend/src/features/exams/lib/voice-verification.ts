import { DEFAULT_EXAM_SERVER_URL } from '../constants';

function httpUrl(serverUrl: string) {
  return serverUrl.replace(/^wss?:\/\//, (m) => (m.startsWith('wss') ? 'https://' : 'http://'));
}

export async function checkVoiceReference(userId: string, serverUrl = DEFAULT_EXAM_SERVER_URL): Promise<boolean> {
  const base = httpUrl(serverUrl);
  const res = await fetch(`${base}/voice-reference?user_id=${encodeURIComponent(userId)}`);
  if (!res.ok) return false;
  const data = (await res.json()) as { exists: boolean };
  return data.exists === true;
}

export async function uploadVoiceReference({
  userId,
  audioBlob,
  serverUrl = DEFAULT_EXAM_SERVER_URL,
}: {
  userId: string;
  audioBlob: Blob;
  serverUrl?: string;
}): Promise<void> {
  const base = httpUrl(serverUrl);
  const form = new FormData();
  form.append('user_id', userId);
  form.append('audio', audioBlob, 'voice-reference.webm');

  const res = await fetch(`${base}/voice-reference`, { method: 'POST', body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { detail?: string }).detail ?? `Upload failed (${res.status})`);
  }
}
