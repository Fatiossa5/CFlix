// These are event-flow tests with small DOM/video doubles, not browser tests.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createPlayerControls} from '../public/player.js';

class ElementDouble extends EventTarget {
  constructor(tagName='DIV') {
    super(); this.tagName=tagName; this.hidden=true; this.style={}; this.value='';
    this.disabled=false; this.textContent=''; this.attributes={}; this.children=[];
    const classes=new Set();
    this.classList={add:(...values)=>values.forEach(value=>classes.add(value)),
      remove:(...values)=>values.forEach(value=>classes.delete(value)), contains:value=>classes.has(value)};
  }
  setAttribute(name,value){this.attributes[name]=value;}
  contains(){return false;}
  replaceChildren(...children){this.children=children;}
  querySelector(selector){if(selector==='strong')return this.strong ||= new ElementDouble('STRONG');throw new Error(selector);}
}

class VideoDouble extends ElementDouble {
  constructor(){super('VIDEO');this.currentTime=40;this.duration=300;this.paused=true;this.playbackRate=1;this.volume=1;this.muted=false;this.clientWidth=400;this.src='';this.playCalls=0;}
  pause(){this.paused=true;this.dispatchEvent(new Event('pause'));}
  play(){this.playCalls++;this.paused=false;this.dispatchEvent(new Event('play'));return Promise.resolve();}
  load(){this.currentTime=0;this.duration=NaN;}
  getBoundingClientRect(){return {left:0};}
}

function emit(element,type,properties={}) {
  const event=new Event(type,{cancelable:true});
  for(const [key,value] of Object.entries(properties))Object.defineProperty(event,key,{value});
  element.dispatchEvent(event);
  return event;
}

function fixture(t) {
  const original={document:globalThis.document,localStorage:globalThis.localStorage};
  const nodes=new Map();
  const get=selector=>{if(!nodes.has(selector))nodes.set(selector,new ElementDouble());return nodes.get(selector);};
  get('#player-dialog').open=true;
  const storage=new Map(), messages=[];
  globalThis.document={querySelector:get,createElement:tag=>new ElementDouble(tag.toUpperCase()),activeElement:null};
  globalThis.localStorage={getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value)};
  const video=new VideoDouble();
  const controls=createPlayerControls({video,toast:message=>messages.push(message)});
  const movie={video:'/media/'+'a'.repeat(32),qualities:[{label:'720p',src:'/media/'+'b'.repeat(32)}]};
  controls.reset(movie);
  // app.js invokes this method when the new source emits loadedmetadata.
  video.addEventListener('loadedmetadata',()=>controls.restoreQuality());
  t.after(()=>{controls.close();for(const [key,value] of Object.entries(original)){if(value===undefined)delete globalThis[key];else globalThis[key]=value;}});
  return {get,video,controls,movie,storage,messages};
}

test('forward button accumulates 10+10 feedback and reverse starts a new burst', t=>{
  const {get,video}=fixture(t);
  emit(get('#player-forward'),'click');emit(get('#player-forward'),'click');
  assert.equal(video.currentTime,60);
  assert.equal(get('#seek-forward').querySelector('strong').textContent,'20 saniye');
  assert.equal(get('#seek-forward').classList.contains('visible'),true);
  emit(get('#player-back'),'click');
  assert.equal(video.currentTime,50);
  assert.equal(get('#seek-back').querySelector('strong').textContent,'10 saniye');
  assert.equal(get('#seek-forward').classList.contains('visible'),false);
});

test('resume choice blocks buttons, timeline, playback toggle and quality changes', t=>{
  const {get,video,controls}=fixture(t);
  get('#resume-prompt').hidden=false;
  emit(get('#player-forward'),'click');emit(get('#player-toggle'),'click');
  get('#player-timeline').value=900;emit(get('#player-timeline'),'input');
  get('#player-quality').value='720p';emit(get('#player-quality'),'change');
  assert.equal(video.currentTime,40);
  assert.equal(video.paused,true);
  assert.equal(video.src,'');
  assert.equal(controls.switchingQuality,false);
  assert.equal(get('#player-quality').value,'original');
});

test('quality metadata restores position, playback rate and playing state', t=>{
  const {get,video,controls,movie}=fixture(t);
  video.currentTime=123.5;video.playbackRate=1.5;video.paused=false;
  get('#player-quality').value='720p';emit(get('#player-quality'),'change');
  assert.equal(video.src,movie.qualities[0].src);
  assert.equal(video.paused,true);
  assert.equal(controls.switchingQuality,true);
  assert.equal(get('#player-quality').disabled,true);
  video.duration=250;emit(video,'loadedmetadata');
  assert.equal(video.currentTime,123.5);
  assert.equal(video.playbackRate,1.5);
  assert.equal(video.paused,false);
  assert.equal(controls.switchingQuality,false);
  assert.equal(get('#player-quality').value,'720p');
});

test('paused quality switch remains paused and failed variant falls back at same position', t=>{
  const {get,video,controls,movie,messages}=fixture(t);
  video.currentTime=87;video.paused=true;
  get('#player-quality').value='720p';emit(get('#player-quality'),'change');
  assert.equal(controls.handleError(),true);
  assert.equal(video.src,movie.video);
  video.duration=300;emit(video,'loadedmetadata');
  assert.equal(video.currentTime,87);
  assert.equal(video.paused,true);
  assert.equal(video.playCalls,0);
  assert.equal(get('#player-quality').value,'original');
  assert.equal(messages.length,1);
});

test('volume and brightness sliders update video, labels and persisted preferences', t=>{
  const {get,video,storage}=fixture(t);
  get('#player-volume').value=35;emit(get('#player-volume'),'input');
  get('#player-brightness').value=125;emit(get('#player-brightness'),'input');
  assert.equal(video.volume,0.35);
  assert.equal(get('#volume-value').textContent,'%35');
  assert.equal(video.style.filter,'brightness(125%)');
  assert.equal(get('#brightness-value').textContent,'%125');
  assert.deepEqual(JSON.parse(storage.get('cflix-player')),{volume:0.35,brightness:125});
  get('#player-volume').value=0;emit(get('#player-volume'),'input');
  assert.equal(video.muted,true);
});

test('touch double tap seeks once even when a synthetic dblclick follows', t=>{
  const {video}=fixture(t);
  emit(video,'pointerup',{pointerType:'touch',clientX:350});
  emit(video,'pointerup',{pointerType:'touch',clientX:350});
  emit(video,'dblclick',{clientX:350});
  assert.equal(video.currentTime,50);
});

test('single mouse clicks toggle playback on the video surface', async t=>{
  const {video}=fixture(t);
  emit(video,'click',{detail:1});
  assert.equal(video.paused,true);
  await new Promise(resolve=>setTimeout(resolve,310));
  assert.equal(video.paused,false);
  emit(video,'click',{detail:1});
  await new Promise(resolve=>setTimeout(resolve,310));
  assert.equal(video.paused,true);
});

test('mouse double click seeks without toggling playback', async t=>{
  const {video}=fixture(t);
  video.paused=false;
  emit(video,'click',{detail:1});
  emit(video,'click',{detail:2});
  emit(video,'dblclick',{clientX:350});
  await new Promise(resolve=>setTimeout(resolve,310));
  assert.equal(video.currentTime,50);
  assert.equal(video.paused,false);
  assert.equal(video.playCalls,0);
});

test('pending clicks are cancelled on player close', async t=>{
  const {video,controls}=fixture(t);
  emit(video,'click',{detail:1});controls.close();
  await new Promise(resolve=>setTimeout(resolve,310));
  assert.equal(video.playCalls,0);
});

test('fullscreen requests target the player container, and toggle exits fullscreen', async t=>{
  const {get}=fixture(t);
  let requests=0,exits=0;
  get('#player-dialog').requestFullscreen=()=>{throw new Error('Dialog is not a valid fullscreen target');};
  get('#player-stage').requestFullscreen=async()=>{requests++;document.fullscreenElement=get('#player-stage');};
  document.exitFullscreen=async()=>{exits++;document.fullscreenElement=null;};
  emit(get('#player-fullscreen'),'click');
  await Promise.resolve();
  assert.equal(requests,1);
  emit(get('#player-fullscreen'),'click');
  await Promise.resolve();
  assert.equal(exits,1);
});

test('iOS native fullscreen remains available when the container API is missing', t=>{
  const {get,video}=fixture(t);
  let calls=0;
  video.webkitEnterFullscreen=()=>{calls++;};
  emit(get('#player-fullscreen'),'click');
  assert.equal(calls,1);
  assert.equal(video.controls,true);
  emit(video,'webkitendfullscreen');
  assert.equal(video.controls,false);
});

test('rejected fullscreen falls back to an expandable page player', async t=>{
  const {get,messages}=fixture(t);
  get('#player-stage').requestFullscreen=async()=>{throw new Error('Fullscreen disabled by browser');};
  emit(get('#player-fullscreen'),'click');
  await Promise.resolve();
  assert.equal(get('#player-dialog').classList.contains('fullscreen-fallback'),true);
  assert.equal(messages.length,1);
  emit(get('#player-fullscreen'),'click');
  assert.equal(get('#player-dialog').classList.contains('fullscreen-fallback'),false);
});
