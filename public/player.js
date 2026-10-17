import {seekStep, qualitySources, restorePosition} from './player-core.js';

export function createPlayerControls({video, toast}) {
  const $ = s => document.querySelector(s);
  const dialog=$('#player-dialog');
  const clock=seconds=>`${Math.floor(seconds/60)}:${String(Math.floor(seconds%60)).padStart(2,'0')}`;
  const stage=$('#player-stage');
  let burst=null, feedbackTimer, idleTimer, clickTimer, pending=null, sources=[], selected='original', lastTap=null, lastTouchAt=0;
  const preferences={volume:1,brightness:100};
  try {Object.assign(preferences,JSON.parse(localStorage.getItem('cflix-player')||'{}'));}catch{}
  preferences.volume=Math.max(0,Math.min(1,Number(preferences.volume)||0));
  preferences.brightness=Math.max(25,Math.min(150,Number(preferences.brightness)||100));
  function store(){try{localStorage.setItem('cflix-player',JSON.stringify(preferences));}catch{}}
  function showControls(){dialog.classList.add('controls-visible');clearTimeout(idleTimer);idleTimer=setTimeout(()=>{if(!video.paused && $('#player-settings').hidden && !$('#player-controls').contains(document.activeElement))dialog.classList.remove('controls-visible');},3000);}
  function update(){
    const duration=Number.isFinite(video.duration)?video.duration:0;
    $('#player-clock').textContent=`${clock(video.currentTime||0)} / ${clock(duration)}`;
    $('#player-timeline').value=duration?video.currentTime/duration*1000:0;
    $('#player-timeline').disabled=!duration || !!pending;
    $('#player-timeline').setAttribute('aria-valuetext',`${clock(video.currentTime||0)} / ${clock(duration)}`);
    $('#player-toggle').textContent=video.paused?'▶':'Ⅱ';
    $('#player-toggle').setAttribute('aria-label',video.paused?'Oynat':'Duraklat');
    if(video.paused)showControls();
  }
  function toggle(){if(pending || !$('#resume-prompt').hidden)return;video.paused?video.play().catch(()=>toast('Oynatmak için tekrar dokun.')):video.pause();}
  function seek(direction){
    if(pending || !$('#resume-prompt').hidden)return;
    const next=seekStep(video.currentTime,video.duration,direction,burst,Date.now());
    if(!next)return;
    burst=next; video.currentTime=next.target;
    const active=$(direction<0?'#seek-back':'#seek-forward');
    const other=$(direction<0?'#seek-forward':'#seek-back');
    const text=`${Math.round(next.total*10)/10} saniye`;
    other.classList.remove('visible');active.querySelector('strong').textContent=text;
    active.classList.remove('pulse');void active.offsetWidth;active.classList.add('visible','pulse');
    $('#seek-announcement').textContent=`${text} ${direction<0?'geri':'ileri'} sarıldı`;
    clearTimeout(feedbackTimer);feedbackTimer=setTimeout(()=>{active.classList.remove('visible');burst=null;},900);
    showControls();update();
  }
  $('#player-back').addEventListener('click',()=>seek(-1));
  $('#player-forward').addEventListener('click',()=>seek(1));
  $('#player-toggle').addEventListener('click',toggle);
  $('#player-timeline').addEventListener('input',event=>{if(!pending && $('#resume-prompt').hidden && Number.isFinite(video.duration))video.currentTime=video.duration*Number(event.target.value)/1000;update();showControls();});
  video.addEventListener('click',event=>{
    if(Date.now()-lastTouchAt<500)return;
    clearTimeout(clickTimer);
    if(event.detail>1)return;
    clickTimer=setTimeout(()=>{if(dialog.open){toggle();showControls();}},280);
  });
  video.addEventListener('dblclick',event=>{clearTimeout(clickTimer);if(Date.now()-lastTouchAt<500)return;event.preventDefault();seek(event.clientX<video.getBoundingClientRect().left+video.clientWidth/2?-1:1);});
  video.addEventListener('pointerup',event=>{
    if(event.pointerType==='touch'){
      lastTouchAt=Date.now();
      const side=event.clientX<video.getBoundingClientRect().left+video.clientWidth/2?-1:1;
      const now=Date.now();if(lastTap && now-lastTap.at<320 && lastTap.side===side){event.preventDefault();seek(side);}else showControls();lastTap={at:now,side};
    }else showControls();
  });
  dialog.addEventListener('pointermove',showControls);
  dialog.addEventListener('focusin',showControls);
  dialog.addEventListener('keydown',event=>{
    if(event.key==='Escape' && dialog.classList.contains('fullscreen-fallback')){event.preventDefault();dialog.classList.remove('fullscreen-fallback');return;}
    if(!dialog.open || /INPUT|SELECT|TEXTAREA/.test(event.target.tagName))return;
    if(event.target.tagName==='BUTTON' && (event.code==='Space'||event.key==='Enter'))return;
    if(['ArrowLeft','j','J'].includes(event.key)){event.preventDefault();seek(-1);}
    if(['ArrowRight','l','L'].includes(event.key)){event.preventDefault();seek(1);}
    if(event.code==='Space' || event.key==='k'){event.preventDefault();toggle();}
    if(event.key==='m'){video.muted=!video.muted;}
  });
  $('#player-settings-toggle').addEventListener('click',()=>{
    $('#player-settings').hidden=!$('#player-settings').hidden;
    $('#player-settings-toggle').setAttribute('aria-expanded',String(!$('#player-settings').hidden));showControls();
  });
  $('#player-brightness').value=preferences.brightness;
  $('#brightness-value').textContent=`%${preferences.brightness}`;
  video.style.filter=`brightness(${preferences.brightness}%)`;
  $('#player-brightness').addEventListener('input',event=>{preferences.brightness=Number(event.target.value);video.style.filter=`brightness(${preferences.brightness}%)`;$('#brightness-value').textContent=`%${preferences.brightness}`;store();});
  try{video.volume=preferences.volume;}catch{}
  $('#player-volume').value=video.volume*100;
  $('#volume-value').textContent=`%${Math.round(video.volume*100)}`;
  $('#player-volume').addEventListener('input',event=>{
    const requested=Number(event.target.value)/100;
    try{video.volume=requested;video.muted=requested===0;}catch{}
    if(Math.abs(video.volume-requested)>.02)toast('Bu cihazda ses için cihazın ses düğmelerini kullan.');
    preferences.volume=video.volume;$('#player-volume').value=video.volume*100;$('#volume-value').textContent=`%${Math.round(video.volume*100)}`;store();
  });
  video.addEventListener('volumechange',()=>{$('#volume-value').textContent=`%${video.muted?0:Math.round(video.volume*100)}`;$('#player-volume').value=video.muted?0:video.volume*100;});
  $('#player-fullscreen').addEventListener('click',async()=>{
    if(dialog.classList.contains('fullscreen-fallback')){dialog.classList.remove('fullscreen-fallback');return;}
    try{
      if(document.fullscreenElement){await document.exitFullscreen();return;}
      // Dialog elements cannot be fullscreen targets; use their player container.
      if(stage?.requestFullscreen){await stage.requestFullscreen();return;}
    }catch{}
    try{if(video.webkitEnterFullscreen){video.controls=true;video.webkitEnterFullscreen();return;}}
    catch{video.controls=false;}
    dialog.classList.add('fullscreen-fallback');
    toast('Oynatıcı pencereyi kaplayacak şekilde genişletildi.');
  });
  video.addEventListener('webkitendfullscreen',()=>video.controls=false);
  $('#player-quality').addEventListener('change',event=>{
    if(!$('#resume-prompt').hidden){event.target.value=selected;return;}
    const choice=sources.find(item=>item.value===event.target.value);
    const old=sources.find(item=>item.value===selected);
    if(!choice || choice.value===selected || pending)return;
    pending={position:video.currentTime,playing:!video.paused,rate:video.playbackRate,old,choice,fallback:false};
    $('#player-quality').disabled=true;video.pause();video.src=choice.src;video.load();showControls();
  });
  for(const event of ['timeupdate','play','pause','durationchange','ended'])video.addEventListener(event,update);
  return {
    get switchingQuality(){return !!pending;},
    reset(movie){
      pending=null;burst=null;clearTimeout(feedbackTimer);clearTimeout(clickTimer);lastTap=null;selected='original';sources=qualitySources(movie);
      $('#player-quality').replaceChildren(...sources.map(source=>{const option=document.createElement('option');option.value=source.value;option.textContent=source.label;return option;}));
      $('#player-quality').disabled=sources.length<2;
      $('#quality-note').textContent=sources.length<2?'Bu içerikte yalnızca orijinal sürüm bulunuyor.':'Kalite değiştiğinde izleme konumun korunur.';
      $('#player-settings').hidden=true;$('#player-settings-toggle').setAttribute('aria-expanded','false');
      $('#seek-back').classList.remove('visible');$('#seek-forward').classList.remove('visible');showControls();update();
    },
    restoreQuality(){
      if(!pending)return false;
      const snapshot=pending;video.currentTime=restorePosition(snapshot.position,video.duration);video.playbackRate=snapshot.rate;
      selected=snapshot.choice.value;$('#player-quality').value=selected;$('#player-quality').disabled=sources.length<2;
      pending=null;update();if(snapshot.playing)video.play().catch(()=>toast('Devam etmek için oynat düğmesine bas.'));
      return true;
    },
    handleError(){
      if(!pending)return false;
      if(pending.fallback){pending=null;$('#player-quality').disabled=false;return false;}
      pending.fallback=true;pending.choice=pending.old;video.src=pending.old.src;video.load();toast('Seçilen kalite açılamadı; önceki sürüme dönülüyor.');return true;
    },
    close(){clearTimeout(idleTimer);clearTimeout(feedbackTimer);clearTimeout(clickTimer);pending=null;burst=null;dialog.classList.remove('fullscreen-fallback');$('#player-settings').hidden=true;}
  };
}
