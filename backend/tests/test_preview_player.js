const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const html = fs.readFileSync(path.join(__dirname, '../studio/tts_preview.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const posted = [], sent = [];
const controls = Object.fromEntries(['status','voice','speak','stop','text','answer'].map(id=>[id,{value:'سلام'}]));
let socket, number = 0;
class Socket {
  static OPEN = 1;
  constructor() { this.readyState=1; socket=this; }
  send(message) { sent.push(JSON.parse(message)); }
}
const context = {
  document:{querySelector:selector=>controls[selector.slice(1)]},
  location:{protocol:'http:',host:'localhost:8080'}, WebSocket:Socket,
  crypto:{randomUUID:()=>String(++number)}, Uint8Array, Int16Array, atob,
  AudioContext:class { constructor(){this.audioWorklet={addModule:async()=>{}};} async resume(){} },
  AudioWorkletNode:class { constructor(){this.port={postMessage:message=>posted.push(message)};} connect(){} },
};
vm.runInNewContext(script,context);
const receive = message => socket.onmessage({data:JSON.stringify(message)});
(async()=>{
  await controls.speak.onclick();
  const first = sent.at(-1).request_id;
  controls.stop.onclick();
  posted.length=0;
  receive({type:'tts_begin',request_id:first,generation_id:'old'});
  receive({type:'tts_chunk',request_id:first,generation_id:'old',content:'AQACAA=='});
  assert.equal(posted.length,0,'A begin/PCM response arriving after Stop must stay suppressed');
  await controls.speak.onclick();
  const second = sent.at(-1).request_id;
  receive({type:'tts_begin',request_id:second,generation_id:'new'});
  posted.length=0;
  receive({type:'stop_tts',request_id:first});
  receive({type:'tts_chunk',request_id:first,generation_id:'old',content:'AQACAA=='});
  assert.equal(posted.length,0,'Old stop/audio must not affect the new generation');
  receive({type:'tts_chunk',request_id:second,generation_id:'new',content:'AQACAA=='});
  assert.deepEqual([...posted[0]],[1,2]);
  receive({type:'assistant_partial',request_id:first,generation_id:'old',content:'قديم'});
  assert.equal(controls.answer.textContent,'','Canceled text must not appear in the new turn');
  receive({type:'assistant_partial',request_id:second,generation_id:'new',content:'سلام Sara، الطلب AB-1203.'});
  assert.equal(controls.answer.textContent,'سلام Sara، الطلب AB-1203.');
  console.log('Preview playback cancellation and PCM decoding checks passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
