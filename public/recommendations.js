export const SLIDE_INTERVAL_MS = 10000;

export function nextSlide(index, total, visible, direction=1) {
  const last=Math.max(0,total-Math.max(1,visible));
  if(index+direction>last)return 0;
  if(index+direction<0)return last;
  return index+direction;
}

export function previewWindow(duration) {
  if(!Number.isFinite(duration) || duration<=0)return null;
  const start=duration>30?Math.min(60,duration*.1):0;
  return {start,end:Math.min(duration,start+12)};
}

// Önizleme ayrı bir video öğesidir; izleme geçmişine ilerleme göndermez.
export function mountRecommendations({root,movies,loggedIn}) {
  const track=root.querySelector('.recommendation-track');
  const cards=[...track.querySelectorAll('.card')];
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const saveData=!!navigator.connection?.saveData;
  const button=root.querySelector('[data-carousel-pause]');
  let index=0,paused=reduced,hover=false,focused=false,inView=typeof IntersectionObserver==='undefined',activeVideo=null,activeId=null,scrollTimer;
  const previews=new Map();
  const controller=new AbortController();const {signal}=controller;
  function visibleCount(){const gap=parseFloat(getComputedStyle(track).columnGap)||0;return Math.max(1,Math.round((track.clientWidth+gap)/((cards[0]?.getBoundingClientRect().width||track.clientWidth)+gap)));}
  function blocked(){return paused||hover||focused||document.hidden||!inView||!!document.querySelector('dialog[open]');}
  function mediaBlocked(){return paused||focused||document.hidden||!inView||!!document.querySelector('dialog[open]');}
  function stopPreview(){if(activeVideo){activeVideo.pause();activeVideo.classList.remove('preview-playing');}activeVideo=null;activeId=null;}
  function syncPreview(){
    if(mediaBlocked()||!loggedIn||reduced||saveData){stopPreview();return;}
    const movie=movies[index];if(!movie || movie.demo){stopPreview();return;}
    if(activeId===movie.id)return;
    stopPreview();
    let preview=previews.get(movie.id);
    if(!preview){
      preview=document.createElement('video');preview.className='card-preview';preview.muted=true;preview.playsInline=true;preview.preload='none';preview.tabIndex=-1;preview.setAttribute('aria-hidden','true');
      preview.addEventListener('playing',()=>preview.classList.add('preview-playing'),{signal});
      preview.addEventListener('error',()=>preview.classList.remove('preview-playing'),{signal});
      preview.addEventListener('timeupdate',()=>{const range=previewWindow(preview.duration);if(range&&preview.currentTime>=range.end){preview.pause();preview.classList.remove('preview-playing');}},{signal});
      preview.addEventListener('loadedmetadata',()=>{
        if(preview!==activeVideo||mediaBlocked())return;
        const range=previewWindow(preview.duration);if(!range)return;
        preview.currentTime=range.start;preview.play().catch(()=>preview.classList.remove('preview-playing'));
      },{signal});
      previews.set(movie.id,preview);cards[index].querySelector('.card-art').append(preview);
    }
    activeVideo=preview;activeId=movie.id;
    if(!preview.getAttribute('src')){preview.src=movie.video;preview.load();}
    else{const range=previewWindow(preview.duration);if(range){preview.currentTime=range.start;preview.play().catch(()=>{});}}
  }
  function syncButton(){button.textContent=paused?'▶ Otomatik kaydır':'Ⅱ Kaydırmayı durdur';button.setAttribute('aria-pressed',String(!paused));}
  function move(direction){
    index=nextSlide(index,cards.length,visibleCount(),direction);
    track.scrollTo({left:cards[index]?.offsetLeft||0,behavior:reduced?'instant':'smooth'});syncPreview();
  }
  root.querySelector('[data-carousel-back]').addEventListener('click',()=>{paused=true;syncButton();move(-1);},{signal});
  root.querySelector('[data-carousel-next]').addEventListener('click',()=>{paused=true;syncButton();move(1);},{signal});
  button.addEventListener('click',()=>{paused=!paused;if(!paused)focused=false;syncButton();syncPreview();},{signal});
  root.addEventListener('mouseenter',()=>{hover=true;syncPreview();},{signal});
  root.addEventListener('mouseleave',()=>{hover=false;syncPreview();},{signal});
  root.addEventListener('focusin',()=>{focused=true;stopPreview();},{signal});
  root.addEventListener('focusout',()=>{queueMicrotask(()=>{focused=root.contains(document.activeElement);syncPreview();});},{signal});
  track.addEventListener('scroll',()=>{clearTimeout(scrollTimer);scrollTimer=setTimeout(()=>{
    let nearest=0;for(let i=1;i<cards.length;i++)if(Math.abs(cards[i].offsetLeft-track.scrollLeft)<Math.abs(cards[nearest].offsetLeft-track.scrollLeft))nearest=i;
    index=nearest;syncPreview();
  },180);},{signal,passive:true});
  document.addEventListener('visibilitychange',syncPreview,{signal});
  const observer=new MutationObserver(syncPreview);document.querySelectorAll('dialog').forEach(dialog=>observer.observe(dialog,{attributes:true,attributeFilter:['open']}));
  const intersection=typeof IntersectionObserver==='undefined'?null:new IntersectionObserver(entries=>{inView=entries[0].isIntersecting;syncPreview();},{threshold:.15});intersection?.observe(root);
  const timer=setInterval(()=>{if(!blocked())move(1);},SLIDE_INTERVAL_MS);
  syncButton();syncPreview();
  return {destroy(){controller.abort();clearInterval(timer);clearTimeout(scrollTimer);observer.disconnect();intersection?.disconnect();stopPreview();for(const preview of previews.values()){preview.removeAttribute('src');preview.load();}previews.clear();}};
}
