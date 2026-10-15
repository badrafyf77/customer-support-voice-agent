/** Production frontend against the loopback production-session test harness. */
import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
const front=process.env.VOICE_TEST_FRONTEND || 'http://127.0.0.1:3001';
const backend=process.env.VOICE_TEST_SERVER || 'http://127.0.0.1:8766';
const browser=await chromium.launch({headless:true,args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream']});
const context=await browser.newContext({permissions:['microphone'],viewport:{width:1180,height:900}});
const page=await context.newPage();
const errors=[];
page.on('pageerror',error=>errors.push(error.message));
const post=async(path,payload)=>{
  const result=await context.request.post(backend+path,{data:payload});
  assert.equal(result.ok(),true,await result.text());return result;
};
const spoken='سلام Sara، الطلب AB-1203 واجد. الثمن 12.50 درهم.';
const final=async()=>page.waitForFunction(text=>[...document.querySelectorAll('.message.assistant .message-content')].some(p=>p.textContent===text),spoken);
const report=[];
try {
  await page.addInitScript(()=>{
    window.__sockets=[];window.__audio=[];
    const Socket=window.WebSocket;
    window.WebSocket=class extends Socket {constructor(...args){super(...args);window.__sockets.push(this);}};
    const Node=window.AudioWorkletNode;
    window.AudioWorkletNode=class extends Node {
      constructor(...args){super(...args);if(args[1]==='tts-playback-processor'){
        const post=this.port.postMessage.bind(this.port);
        this.port.postMessage=(data,...rest)=>{window.__audio.push(data?.type || [...data]);return post(data,...rest);};
      }}
    };
  });
  await page.goto(front+'?server='+encodeURIComponent(backend));
  await page.addScriptTag({path:new URL('../../backend/studio/browser_trace.js',import.meta.url).pathname});
  await page.evaluate(()=>window.voiceTrace.mark('utterance_end'));
  await page.getByRole('button',{name:'Start',exact:true}).click();
  await page.getByText('Microphone is streaming.',{exact:true}).waitFor();
  const second=await context.newPage();
  await second.goto(front+'?server='+encodeURIComponent(backend));
  await second.getByRole('button',{name:'Start',exact:true}).click();
  await second.getByRole('alert').filter({hasText:'capacity'}).waitFor();
  assert.equal(await second.getByText('Microphone is streaming.',{exact:true}).count(),0);
  await second.close();
  report.push('Second browser session receives visible capacity feedback without displacing the first');
  await post('/test/turn',{text:'Sara، الطلب AB-1203 والثمن 12.50',partial:'نص مؤقت'});
  await final();
  const timing=await page.evaluate(()=>JSON.stringify(window.voiceTrace.events));
  assert(timing.includes('server:tts_chunk') && timing.includes('generation_id'));
  assert(!timing.includes('Sara') && !timing.includes('AB-1203'));
  report.push('Timing recorder observes production events and excludes transcript/audio content');
  assert.equal(await page.locator('.message.user .message-content').last().textContent(),'Sara، الطلب AB-1203 والثمن 12.50');
  assert.equal(await page.locator('.message.assistant .message-content').last().evaluate(el=>getComputedStyle(el).direction),'rtl');
  assert.equal(await page.locator('.message.assistant').count(),1,'Quick/final text uses one bubble');
  const state=await (await context.request.get(backend+'/test/state')).json();
  assert.ok(state.packets>0,'Real capture worklet sends the unchanged binary packet framing');
  report.push('Production /ws, microphone worklet/framing, final STT, ordered PCM, one final bubble, Arabic direction and identifiers');

  await post('/test/config',{block_stream:true});
  await post('/test/turn',{text:'الapplication ديال delivery ما خداماش'});
  await page.waitForFunction(()=>document.querySelectorAll('.message.assistant').length>=2);
  await post('/test/config',{block_stream:false});
  await post('/test/turn',{text:'لا، بغيت نبدل العنوان'});
  await page.waitForFunction(()=>[...document.querySelectorAll('.message.assistant .message-content')].filter(el=>el.textContent==='سلام Sara، الطلب AB-1203 واجد. الثمن 12.50 درهم.').length>=2);
  report.push('Interruption between quick/final phrases, immediate next turn, foreign input terms retained');

  await page.getByRole('button',{name:'Reset Transcript'}).click();
  await page.getByText('Conversation will appear here.').waitFor();
  await post('/test/turn',{text:'جديد Sara 0612345678'});
  await final();
  const resetState=await (await context.request.get(backend+'/test/state')).json();
  assert.equal(resetState.requests.at(-1).messages.length,1);
  report.push('Reset clears browser transcript, playback and server conversation history');

  await post('/test/config',{fail:true});
  await post('/test/turn',{text:'جرب دابا'});
  await page.getByRole('alert').filter({hasText:'Speech generation failed'}).waitFor();
  await page.getByRole('button',{name:'Start',exact:true}).waitFor({state:'visible'});
  await page.waitForFunction(()=>!document.querySelector('.primary-button').disabled);
  assert.equal(await page.getByText('Microphone is streaming.',{exact:true}).count(),0);
  report.push('Model service failure is visible, playback/capture stop, runtime returns for a clean reconnect');

  await post('/test/config',{fail:false});
  await page.getByRole('button',{name:'Start',exact:true}).click();
  await page.getByText('Microphone is streaming.',{exact:true}).waitFor();
  await page.evaluate(()=>{
    const old=window.__sockets.filter(socket=>new URL(socket.url).pathname==='/ws')[0];
    old.onmessage({data:JSON.stringify({type:'assistant_partial',content:'STALE TEXT',generation_id:9999})});
    old.onclose({});
  });
  assert.equal(await page.getByText('STALE TEXT',{exact:true}).count(),0);
  assert.equal(await page.getByText('Microphone is streaming.',{exact:true}).count(),1);
  assert.equal(await page.locator('.message').count(),0);
  await post('/test/turn',{text:'جلسة جديدة'});
  await final();
  const reconnect=await (await context.request.get(backend+'/test/state')).json();
  assert.equal(reconnect.requests.at(-1).messages.length,1);
  report.push('Old socket callbacks ignored; reused runtime and browser both start with empty history');
  await page.evaluate(()=>{
    const socket=window.__sockets.filter(socket=>new URL(socket.url).pathname==='/ws').at(-1);
    const deliver=payload=>socket.onmessage({data:JSON.stringify(payload)});
    deliver({type:'tts_chunk',generation_id:100,content:'AQACAA=='});
    deliver({type:'stop_tts',generation_id:100});
    deliver({type:'tts_chunk',generation_id:100,content:'AwAEAA=='});
    deliver({type:'tts_chunk',generation_id:101,content:'BQAGAA=='});
    deliver({type:'stop_tts',generation_id:100});
  });
  const audio=await page.evaluate(()=>window.__audio.slice(-3));
  assert.deepEqual(audio,[[1,2],'clear',[5,6]],'Late old PCM and Stop cannot affect replacement audio');
  await mkdir('tests/.artifacts',{recursive:true});
  await page.screenshot({path:'tests/.artifacts/darija-chat.png',fullPage:true});
  await page.getByRole('button',{name:'Stop',exact:true}).click();
  report.push('Scoped old PCM and Stop rejected; actual production playback worklet is used');
  const delayed=await context.newPage();
  await delayed.addInitScript(()=>{
    const original=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia=constraints=>new Promise(resolve=>{
      window.__permissionPending=true;
      window.__releaseMic=async()=>{window.__lateStream=await original(constraints);resolve(window.__lateStream);};
    });
  });
  await delayed.goto(front+'?server='+encodeURIComponent(backend));
  await delayed.getByRole('button',{name:'Start',exact:true}).click();
  await delayed.waitForFunction(()=>window.__permissionPending===true);
  await delayed.getByRole('button',{name:'Stop',exact:true}).click();
  await delayed.evaluate(()=>window.__releaseMic());
  await delayed.waitForFunction(()=>window.__lateStream?.getTracks().every(track=>track.readyState==='ended'));
  assert.equal(await delayed.getByText('Microphone is streaming.',{exact:true}).count(),0);
  await delayed.close();
  report.push('Stopping during microphone setup closes a stream granted after cancellation');
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({passed:true,checks:report,live_models:false,audible_quality_review:false},null,2));
} finally {await context.close();await browser.close();}
