// The optional timing recorder must never copy transcript/audio into the trace.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

class Socket {
  constructor() { this.listeners = {}; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  send() {}
}
class Worklet {
  constructor() {
    this.port = { addEventListener: (_, callback) => { this.callback = callback; }, start() {} };
  }
}
const window = { WebSocket: Socket, AudioWorkletNode: Worklet };
const context = vm.createContext({ window, performance: { now: () => 123 },
  console, setTimeout, Blob, URL, Number, document: {} });
const source = fs.readFileSync(path.join(__dirname, '../studio/browser_trace.js'), 'utf8');
vm.runInContext(source, context);
const socket = new window.WebSocket('ws://localhost/ws');
socket.listeners.message({ data: JSON.stringify({ type: 'final_user_request', content: 'PRIVATE TRANSCRIPT' }) });
socket.listeners.message({ data: JSON.stringify({ type: 'tts_chunk', content: 'PRIVATE AUDIO', generation_id: 7 }) });
socket.send(JSON.stringify({ type: 'clear_history', private: 'PRIVATE SECRET' }));
const worklet = new window.AudioWorkletNode({ sampleRate: 24000, baseLatency: .01 }, 'tts-playback-processor');
worklet.callback({ data: { type: 'ttsPlaybackStarted' } });
window.voiceTrace.mark('utterance_end');
const trace = JSON.stringify(window.voiceTrace.events);
assert(!trace.includes('PRIVATE'));
assert(trace.includes('generation_id'));
assert(trace.includes('playback:ttsPlaybackStarted'));
assert(trace.includes('mark:utterance_end'));
assert.throws(() => vm.runInContext(source, context), /Restore the existing/);
window.voiceTrace.restore();
assert.equal(window.WebSocket, Socket);
assert.equal(window.AudioWorkletNode, Worklet);
assert.equal(window.voiceTrace, undefined);
console.log('Browser timing trace preserves event metadata, excludes transcript/audio and restores APIs');
