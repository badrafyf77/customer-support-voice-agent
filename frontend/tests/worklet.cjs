const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
let Processor;
const events=[];
vm.runInNewContext(fs.readFileSync(require.resolve('../public/static/ttsPlaybackProcessor.js'),'utf8'),{
  AudioWorkletProcessor:class {constructor(){this.port={postMessage:event=>events.push(event)};}},
  registerProcessor:(name,Class)=>{Processor=Class;},
});
const player=new Processor();
const send=data=>player.port.onmessage({data});
const render=count=>{const output=new Float32Array(count);player.process([],[[output]]);return [...output];};
send(new Int16Array([100,200]));send(new Int16Array([300,400,500]));
assert.deepEqual(render(3),[100,200,300].map(v=>v/32768));
assert.deepEqual(render(3),[400/32768,500/32768,0]);
render(1);
assert.deepEqual(events.map(e=>e.type),['ttsPlaybackStarted','ttsPlaybackStopped']);
send(new Int16Array([1000,2000,3000]));render(1);send({type:'clear'});
assert.equal(events.at(-1).type,'ttsPlaybackStopped','Clear synchronizes the server playback flag');
assert.deepEqual(render(4),[0,0,0,0],'Canceled tails never return');
send(new Int16Array([77,88]));assert.deepEqual(render(3),[77/32768,88/32768,0]);
console.log('Production worklet phrase ordering, final tail, clear and replacement PCM checks passed');
