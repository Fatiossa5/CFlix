import {createPlayerControls} from './player.js';
import {mountRecommendations} from './recommendations.js';
const $ = (selector) => document.querySelector(selector);
document.addEventListener('error', event => {
  if (event.target instanceof HTMLImageElement) event.target.style.opacity = '0';
}, true);
const state = { movies: [], user: null, recommendations: [], view: 'home', genre: 'all', search: '' };
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const photo = (movie, width=700) => movie.cover || (movie.photo ? `https://images.unsplash.com/${movie.photo}?auto=format&fit=crop&w=${width}&q=80` : '/poster.svg');
const movieById = id => state.movies.find(movie => movie.id === id);
const time = seconds => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2,'0')}`;
let toastTimer, authMode = 'login', currentMovie = null, resumeTimer, lastSave = 0, pendingAction = null, choosingResume = false;
let progressQueue=Promise.resolve();
let recommendationCarousel=null;
const video = $('#video');
const playerControls = createPlayerControls({video, toast});

async function api(path, data, options={}) {
  const response = await fetch(`/api/${path}`, { method: data === undefined ? 'GET' : 'POST', headers: data === undefined ? {} : {'Content-Type':'application/json'}, body: data === undefined ? undefined : JSON.stringify(data), ...options });
  const result = await response.json();
  if (!response.ok) {
    if (response.status === 401 && (!['login','register','password'].includes(path) || result.code==='auth_required' || result.code==='password_changed')) { state.user = null; updateProfile(); }
    const error=new Error(result.error || 'İşlem tamamlanamadı.');error.status=response.status;error.code=result.code;throw error;
  }
  return result;
}
function toast(message) {
  clearTimeout(toastTimer);const element=$('#toast');element.textContent=message;element.hidden=false;
  try{if(!element.matches(':popover-open'))element.showPopover?.();}catch{}
  toastTimer=setTimeout(()=>{try{element.hidePopover?.();}catch{}element.hidden=true;},3500);
}
function openDialog(id) { const dialog = $(`#${id}`); if (!dialog.open) dialog.showModal(); syncScrollLock(); }
let lockedScroll=null;
function syncScrollLock(){
  const hasDialog=!!document.querySelector('dialog[open]');
  if(hasDialog && lockedScroll===null){lockedScroll=window.scrollY;document.body.style.top=`-${lockedScroll}px`;document.body.classList.add('modal-open');}
  else if(!hasDialog && lockedScroll!==null){const position=lockedScroll;lockedScroll=null;document.body.classList.remove('modal-open');document.body.style.top='';window.scrollTo({top:position,behavior:'instant'});}
}
document.querySelectorAll('dialog').forEach(dialog=>new MutationObserver(syncScrollLock).observe(dialog,{attributes:true,attributeFilter:['open']}));
let noticeTimer;
function sessionNotice(name, entering=true){
  clearTimeout(noticeTimer);const notice=$('#session-notice');
  $('#session-notice-title').textContent=entering?`Hoş geldiniz Sayın ${name}`:`Görüşmek üzere Sayın ${name}`;
  $('#session-notice-message').textContent=entering?'CFlix dünyasına hoş geldiniz.':'Oturumunuz güvenle kapatıldı.';
  notice.hidden=false;notice.classList.remove('arrive');void notice.offsetWidth;notice.classList.add('arrive');
  try{if(!notice.matches(':popover-open'))notice.showPopover?.();}catch{}
  noticeTimer=setTimeout(()=>{try{notice.hidePopover?.();}catch{}notice.hidden=true;},4200);
}
function updateProfile() {
  $('#profile-name').textContent = state.user?.name || 'Giriş yap';
  $('#avatar').textContent = (state.user?.name || 'C')[0].toLocaleUpperCase('tr');
  $('#list-count').textContent = state.user?.favorites.length || 0;
  $('#join-banner').hidden = !!state.user;
  $('#admin-link').hidden = state.user?.role !== 'admin';
  $('#account-admin').hidden = state.user?.role !== 'admin';
  if (state.user) {
    $('#account-name').textContent = state.user.name;
    $('#account-email').textContent = state.user.email;
    $('#profile-avatar').textContent = state.user.name[0].toLocaleUpperCase('tr');
  }
}
async function refreshMe() { if (!state.user) return; const data = await api('me'); state.user = data.user; state.recommendations = data.recommendations; updateProfile(); }

function card(movie) {
  const saved = state.user?.favorites.includes(movie.id);
  const history = state.user?.history[movie.id];
  const progress = history ? Math.min(100,history.position/history.duration*100) : 0;
  return `<article class="card"><div class="card-art"><img src="${photo(movie)}" alt="" loading="lazy"><span class="card-brand">C</span><span class="card-label">${movie.year === 2026 ? 'YENİ' : movie.type.toLocaleUpperCase('tr')}</span><div class="card-art-title"><small>CFlix ORIGINAL</small>${escape(movie.title)}</div><button class="card-play" data-detail="${movie.id}" aria-label="${escape(movie.title)} detaylarını gör"><span>▶</span></button><button class="fav-button ${saved?'saved':''}" data-fav="${movie.id}" aria-label="${escape(movie.title)} ${saved?'listemden çıkar':'listeme ekle'}" aria-pressed="${!!saved}">${saved?'✓':'+'}</button>${history?`<div class="progress-track"><i style="width:${progress}%"></i></div>`:''}</div><div class="card-info"><h3>${escape(movie.title)}</h3><div class="card-meta"><span>${movie.year}</span><span>·</span><span>${movie.genre}</span><span class="rating">★ ${movie.rating.toFixed(1)}</span></div>${history && state.view==='history'?`<div class="progress-caption">${history.completed?'Tamamlandı':`${time(history.position)} / ${time(history.duration)}`} · ${new Date(history.updatedAt).toLocaleDateString('tr-TR')}</div>`:''}</div></article>`;
}
function shelf(title, movies, subtitle='', extra='') { if (!movies.length) return ''; return `<section class="shelf"><div class="shelf-heading"><h2>${title}</h2>${subtitle?`<p>${subtitle}</p>`:''}<span class="shelf-count">${movies.length} içerik</span></div><div class="card-grid ${extra}">${movies.map(card).join('')}</div></section>`; }
function empty(title,description,action='') { return `<div class="empty-state"><span class="empty-icon">◇</span><h3>${title}</h3><p>${description}</p>${action}</div>`; }
function render() {
  recommendationCarousel?.destroy();recommendationCarousel=null;
  document.body.classList.toggle('compact-view',state.view!=='home' || !!state.search);
  $('#admin-section').hidden=state.view!=='admin';
  $('#catalog').hidden=state.view==='admin';
  $('#join-banner').hidden=!!state.user || state.view==='admin';
  if(state.view==='admin') { renderAdmin(); return; }
  document.querySelectorAll('nav [data-view]').forEach(link=>link.classList.toggle('active',link.dataset.view===state.view));
  $('#active-category').textContent=state.genre==='all'?'Kategorileri Filmler ve Diziler menülerinden keşfet.':`Seçili kategori: ${state.genre}`;
  const titles = {home:state.user?`Bu akşam ne izlesek, ${state.user.name}?`:'Bu akşam ne izlesek?',films:'Her film, başka bir dünya.',series:'Bir bölüm daha?',favorites:'Senin listen, senin dünyan.',history:'İz bırakan hikâyelerin.'};
  $('#welcome-title').textContent = state.search ? `“${state.search}” için sonuçlar` : titles[state.view];
  const visible = state.movies.filter(movie => (state.genre==='all' || movie.genre===state.genre) && (!state.search || `${movie.title} ${movie.genre} ${movie.description}`.toLocaleLowerCase('tr').includes(state.search.toLocaleLowerCase('tr'))));
  let html = '';
  if (['favorites','history'].includes(state.view) && !state.user) {
    html = empty('Hikâyelerin sana özel.', 'Favorilerini ve izleme geçmişini görmek için hesabına giriş yap.', '<button class="button primary" data-auth>Giriş yap →</button>');
  } else if (state.view==='favorites') {
    const list = visible.filter(m=>state.user.favorites.includes(m.id));
    html = shelf('Listem',list) || empty('Listende yeni hikâyelere yer var.',state.genre!=='all'||state.search?'Bu filtrede kayıtlı favorin bulunamadı.':'İçeriklerin üzerindeki + düğmesiyle favorilerini burada biriktirebilirsin.');
  } else if (state.view==='history') {
    const list = visible.filter(m=>state.user.history[m.id]).sort((a,b)=>new Date(state.user.history[b.id].updatedAt)-new Date(state.user.history[a.id].updatedAt));
    html = shelf('İzleme geçmişim',list,'En son izlediğinden başlayarak') || empty('İlk hikâyen seni bekliyor.','İzlediğin içerikler, izleme konumlarıyla birlikte burada görünecek.');
  } else if (state.view==='films' || state.view==='series' || state.search || state.genre!=='all') {
    const list = visible.filter(m=>state.view==='films'?m.type==='Film':state.view==='series'?m.type==='Dizi':true);
    html = shelf(state.search?'Arama sonuçları':state.view==='films'?'Filmler':state.view==='series'?'Diziler':state.genre,list) || empty('Henüz bir eşleşme yok.','Başka bir kelime veya tür seçerek yeni bir hikâye keşfet.');
  } else {
    html += shelf('Kütüphaneye yeni eklenenler',visible.filter(m=>!m.demo),'Artık CFlix’te');
    const continued = visible.filter(m=>{ const h=state.user?.history[m.id]; return h && h.position>0 && !h.completed; }).sort((a,b)=>new Date(state.user.history[b.id].updatedAt)-new Date(state.user.history[a.id].updatedAt));
    html += shelf('Kaldığın yerden devam et',continued.slice(0,5),'Hikâyen burada seni bekliyor','continue-grid');
    const recommended = state.recommendations.length ? state.recommendations.map(movieById).filter(Boolean) : [...visible].sort((a,b)=>b.rating-a.rating);
    const picks=[...recommended.filter(movie=>!movie.demo),...recommended.filter(movie=>movie.demo)];
    html += `<section class="shelf recommendation-shelf" id="recommendations" aria-label="Sana önerilen içerikler" aria-roledescription="karusel"><div class="shelf-heading"><h2><span>✧</span> Senin için seçtiklerimiz</h2><div class="carousel-actions"><button data-carousel-pause aria-pressed="true">Ⅱ Kaydırmayı durdur</button><button data-carousel-back aria-label="Önceki öneriler">‹</button><button data-carousel-next aria-label="Sonraki öneriler">›</button></div></div><p class="carousel-hint">Yeni hikâyeler yanından geçsin.${state.user?' Yüklenen içeriklerin kısa, sessiz önizlemeleri otomatik oynar.':''}</p><div class="recommendation-track">${picks.map(card).join('')}</div></section>`;
    html += shelf('Şimdi keşfet',visible.filter(m=>m.year===2026).concat(visible.filter(m=>m.year!==2026)).slice(0,5),'Yeni hikâyeler, yeni dünyalar');
    html += shelf('Bir bölüm daha',visible.filter(m=>m.type==='Dizi').slice(0,5),'Sürükleyici diziler');
  }
  $('#content').innerHTML=html;
  const carousel=$('#recommendations');
  if(carousel){
    const recommended=state.recommendations.length?state.recommendations.map(movieById).filter(Boolean):[...state.movies].sort((a,b)=>b.rating-a.rating);
    recommendationCarousel=mountRecommendations({root:carousel,movies:[...recommended.filter(movie=>!movie.demo),...recommended.filter(movie=>movie.demo)],loggedIn:!!state.user});
  }
}
function navigate(route) {
  const [view,genre]=route.split('/');
  state.view=['home','films','series','favorites','history','admin'].includes(view)?view:'home';
  try{state.genre=genre?decodeURIComponent(genre):'all';}catch{state.genre='all';}
  state.search='';$('#search').value='';setSearchExpanded(false);
  document.querySelectorAll('.nav-category').forEach(item=>{item.classList.remove('menu-open');item.querySelector('button').setAttribute('aria-expanded','false');});
  if(document.activeElement?.closest('.nav-category'))document.activeElement.blur();
  render();window.scrollTo({top:0,behavior:'instant'});
}
window.addEventListener('hashchange',()=>navigate(location.hash.slice(1)));
function setAuthMode(mode) {
  authMode=mode;
  const register=mode==='register';
  $('#auth-title').textContent=register?'Hesap oluştur':'Giriş yap';
  $('#auth-subtitle').textContent=register?'Bir hesap oluştur, kendi izleme dünyanı kur.':'Listelerin ve kaldığın yerdeki hikâyeler seni bekliyor.';
  $('#name-label').hidden=!register; $('#auth-form').elements.name.required=register;
  $('#auth-form').elements.name.disabled=!register;
  $('#auth-form').elements.password.autocomplete=register?'new-password':'current-password';
  $('#auth-submit').textContent=register?'Hesap oluştur →':'Giriş yap →';
  $('#auth-switch-label').textContent=register?'Zaten üye misin?':'Henüz üye değil misin?';
  $('#auth-switch').textContent=register?'Giriş yap':'Hemen katıl'; $('#auth-error').textContent='';
}
function auth(action=null, mode='login') { pendingAction=action; setAuthMode(mode); openDialog('auth-dialog'); }
$('#auth-switch').addEventListener('click',()=>setAuthMode(authMode==='login'?'register':'login'));
$('#auth-form').addEventListener('submit',async event=>{
  event.preventDefault(); const form=event.currentTarget; const submit=$('#auth-submit'); submit.disabled=true; $('#auth-error').textContent='';
  try {
    const data=await api(authMode,Object.fromEntries(new FormData(form))); state.user=data.user;
    await refreshMe(); const action=pendingAction;pendingAction=null;const name=state.user.name;$('#auth-dialog').close(); form.reset(); render();
    if(action) await action();sessionNotice(name);
  } catch(error) { $('#auth-error').textContent=error.message; } finally { submit.disabled=false; }
});
$('#profile-button').addEventListener('click',()=>state.user?openDialog('profile-dialog'):auth());
$('#join-button').addEventListener('click',()=>auth(null,'register'));
$('#account-history').addEventListener('click',()=>{ $('#profile-dialog').close(); location.hash='history'; });
$('#account-admin').addEventListener('click',()=>$('#profile-dialog').close());
$('#logout-button').addEventListener('click',()=>{$('#logout-error').textContent='';openDialog('logout-dialog');});
$('#logout-confirm').addEventListener('click',async event=>{
  event.currentTarget.disabled=true;
  try{const name=state.user?.name||'';await api('logout',{});state.user=null;state.recommendations=[];stagedVideo=null;stagedCover=null;stagedQuality=null;
    $('#logout-dialog').close();$('#profile-dialog').close();updateProfile();render();sessionNotice(name,false);
  }catch(error){$('#logout-error').textContent=error.message;}finally{$('#logout-confirm').disabled=false;}
});
function settingsTab(which,focus=false){
  for(const name of ['password','feedback']){
    const active=name===which;const tab=$(`#settings-${name}-tab`);
    tab.classList.toggle('active',active);tab.setAttribute('aria-selected',String(active));tab.tabIndex=active?0:-1;$(`#settings-${name}-panel`).hidden=!active;
  }
  if(focus)$(`#settings-${which}-tab`).focus();
}
for(const name of ['password','feedback']){
  $(`#settings-${name}-tab`).addEventListener('click',()=>settingsTab(name));
  $(`#settings-${name}-tab`).addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();settingsTab(event.key==='Home'?'password':event.key==='End'?'feedback':name==='password'?'feedback':'password',true);}});
}
$('#account-settings').addEventListener('click',()=>{
  $('#profile-dialog').close();$('#password-form').reset();$('#password-error').textContent='';$('#feedback-error').textContent='';$('#feedback-status').textContent='';settingsTab('password');
  for(const input of $('#password-form').querySelectorAll('input'))input.type='password';$('#password-visibility').setAttribute('aria-pressed','false');$('#password-visibility').textContent='Şifreleri göster';
  openDialog('settings-dialog');checkServerVersion();
});
$('#password-visibility').addEventListener('click',event=>{
  const show=event.currentTarget.getAttribute('aria-pressed')!=='true';for(const input of $('#password-form').querySelectorAll('input'))input.type=show?'text':'password';
  event.currentTarget.setAttribute('aria-pressed',String(show));event.currentTarget.textContent=show?'Şifreleri gizle':'Şifreleri göster';
});
async function checkServerVersion(){
  let health=null;try{const response=await fetch('/api/health',{cache:'no-store'});if(response.ok)health=await response.json();}catch{}
  const current=health?.features?.includes('password') && health?.features?.includes('feedback') && health?.features?.includes('gmail-smtp');
  const banner=$('#server-update-banner');banner.hidden=!!current;
  banner.textContent=current?'':'Açık sunucu eski sürümde veya bağlantı kurulamadı. Eski CFlix konsolunu Ctrl+C ile kapatıp baslat.bat dosyasını yeniden açın; ardından Ctrl+F5 ile sayfayı yenileyin.';
  return health;
}
async function requireFeature(feature){const health=await checkServerVersion();if(!health?.features?.includes(feature))throw new Error('Sunucu güncellenmemiş. Eski sunucuyu Ctrl+C ile kapatıp baslat.bat ile yeniden başlatın ve tekrar giriş yapın.');}
$('#password-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;const data=Object.fromEntries(new FormData(form));const button=form.querySelector('button[type="submit"]');
  $('#password-error').textContent='';if(data.newPassword!==data.confirmPassword){$('#password-error').textContent='Yeni şifreler birbiriyle eşleşmiyor.';return;}
  button.disabled=true;
  try{await requireFeature('password');await api('password',{currentPassword:data.currentPassword,newPassword:data.newPassword});form.reset();$('#settings-dialog').close();toast('Şifren güncellendi. Diğer cihazlardaki oturumlar kapatıldı.');}
  catch(error){
    if(error.code==='auth_required'||error.code==='password_changed'){$('#settings-dialog').close();auth(()=>$('#account-settings').click());toast('Oturumun yenilenmeli. Tekrar giriş yap.');}
    else $('#password-error').textContent=error.message;
  }finally{button.disabled=false;}
});
$('#feedback-form').addEventListener('submit',async event=>{
  event.preventDefault();const form=event.currentTarget;const button=form.querySelector('button[type="submit"]');const data=Object.fromEntries(new FormData(form));
  $('#feedback-error').textContent='';$('#feedback-status').textContent='';button.disabled=true;
  try{await requireFeature('feedback');const result=await api('feedback',data);form.reset();$('#feedback-status').textContent=result.message || (result.status==='sent'?'Mesajın yönetime gönderildi.':'Mesajın kaydedildi; e-posta teslimi bekleniyor.');}
  catch(error){$('#feedback-error').textContent=error.message;}finally{button.disabled=false;}
});
document.querySelectorAll('[data-close]').forEach(button=>button.addEventListener('click',()=>$(`#${button.dataset.close}`).close()));
document.querySelectorAll('dialog:not(#player-dialog)').forEach(dialog=>dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}}));
$('#auth-dialog').addEventListener('close',()=>{pendingAction=null;});
function setSearchExpanded(expanded){$('#search-form').classList.toggle('expanded',expanded);$('.header').classList.toggle('searching',expanded);$('#search-toggle').setAttribute('aria-expanded',String(expanded));}
$('#search-form').addEventListener('submit',event=>event.preventDefault());
$('#search-form').addEventListener('click',event=>{if(!event.target.closest('#search-close')){setSearchExpanded(true);$('#search').focus();}});
$('#search-toggle').addEventListener('click',()=>{setSearchExpanded(true);$('#search').focus();});
$('#search').addEventListener('focus',()=>setSearchExpanded(true));
$('#search-close').addEventListener('click',()=>{state.search='';$('#search').value='';setSearchExpanded(false);$('#search-toggle').focus();render();});
$('#search').addEventListener('input',event=>{state.search=event.target.value.trim();if(state.view==='admin')state.view='home';render();});
$('#search-form').addEventListener('keydown',event=>{if(event.key==='Escape'){$('#search-close').click();event.stopPropagation();}});
const genres=['Bilim Kurgu','Aksiyon','Dram','Gerilim','Belgesel','Macera','Romantik'];
for(const [id,scope] of [['film-genres','films'],['series-genres','series']]){
  $(`#${id}`).innerHTML=`<a href="#${scope}">Tümü</a>`+genres.map(genre=>`<a href="#${scope}/${encodeURIComponent(genre)}">${genre}</a>`).join('');
}
document.querySelectorAll('.category-toggle').forEach(button=>button.addEventListener('click',()=>{const parent=button.closest('.nav-category');const open=parent.classList.toggle('menu-open');button.setAttribute('aria-expanded',String(open));}));
document.querySelectorAll('.nav-category').forEach(item=>{
  item.addEventListener('keydown',event=>{if(event.key==='Escape'){item.classList.remove('menu-open');const toggle=item.querySelector('button');toggle.setAttribute('aria-expanded','false');toggle.focus();}});
  item.addEventListener('focusout',()=>queueMicrotask(()=>{if(!item.contains(document.activeElement)){item.classList.remove('menu-open');item.querySelector('button').setAttribute('aria-expanded','false');}}));
});
document.addEventListener('pointerdown',event=>{if(!event.target.closest('.nav-category'))document.querySelectorAll('.nav-category').forEach(item=>{item.classList.remove('menu-open');item.querySelector('button').setAttribute('aria-expanded','false');});});

async function favorite(id) {
  if (!state.user) return auth(()=>favorite(id));
  try { const data=await api('favorites',{id}); state.user=data.user; state.recommendations=data.recommendations; updateProfile(); render(); if($('#detail-dialog').open)detail(id); toast(state.user.favorites.includes(id)?'Listene eklendi.':'Listenden çıkarıldı.'); }catch(error){toast(error.message);}
}
function detail(id) {
  const movie=movieById(id); if(!movie)return;
  $('#detail-content').innerHTML=`<div class="detail-image" style="background-image:url('${photo(movie,1200)}')"></div><div class="detail-body"><div class="eyebrow">${movie.demo?'ÖRNEK KATALOG':'CFlix KÜTÜPHANE'}</div><h2>${escape(movie.title)}</h2><div class="metadata"><span class="match">${movie.rating ? `★ ${movie.rating.toFixed(1)}` : 'Yeni içerik'}</span><span>${movie.year}</span><span>${movie.type}</span><span>${movie.genre}</span></div><p>${escape(movie.description)}</p><div class="detail-buttons"><button class="button primary" data-play="${id}">▶ Hemen izle</button><button class="button secondary" data-fav="${id}">${state.user?.favorites.includes(id)?'✓ Listemde':'+ Listeme ekle'}</button></div><p class="detail-note">${movie.demo?'Bu örnek içerik tanıtım videosunu oynatır. Görseller temsilidir.':'Bu içerik yönetici tarafından yüklenen videoyu oynatır.'}</p></div>`;
  openDialog('detail-dialog');
}
document.addEventListener('click',event=>{
  const target=event.target.closest('[data-detail],[data-fav],[data-play],[data-auth]'); if(!target)return;
  if(target.hasAttribute('data-detail'))detail(target.dataset.detail);
  if(target.hasAttribute('data-fav'))favorite(target.dataset.fav);
  if(target.hasAttribute('data-play'))play(target.dataset.play);
  if(target.hasAttribute('data-auth'))auth();
});
$('#hero-detail').addEventListener('click',()=>detail('aurora'));
$('#hero-play').addEventListener('click',()=>play('aurora'));

async function play(id) {
  if (!state.user) return auth(()=>play(id));
  const movie=movieById(id); if(!movie)return;
  if($('#detail-dialog').open)$('#detail-dialog').close();
  currentMovie=movie; lastSave=0; choosingResume=false; clearTimeout(resumeTimer);
  playerControls.reset(movie);
  $('#player-title').textContent=movie.title; $('#player-error').textContent=''; $('#resume-prompt').hidden=true;
  $('.sample-label').hidden=!movie.demo;
  openDialog('player-dialog'); video.src=movie.video; video.load();
}
video.addEventListener('loadedmetadata',()=>{
  if(!currentMovie || !$('#player-dialog').open)return;
  if(playerControls.restoreQuality())return;
  const history=state.user?.history[currentMovie.id];
  if(history && history.position>0 && !history.completed && history.position<video.duration-1) {
    choosingResume=true; video.pause(); $('#resume-position').textContent=`${time(history.position)} konumunda bırakmıştın. 3 saniye sonra otomatik devam eder.`;
    $('#resume-prompt').hidden=false; const bar=$('#resume-bar'); bar.classList.remove('running'); void bar.offsetWidth; bar.classList.add('running');
    resumeTimer=setTimeout(()=>chooseResume(true),3000);
  } else { video.currentTime=0; startVideo(); }
});
function startVideo() { video.play().catch(()=>toast('Oynatmak için videodaki ▶ düğmesine bas.')); }
function chooseResume(resume) {
  if(!currentMovie || !choosingResume)return;
  clearTimeout(resumeTimer); const h=state.user?.history[currentMovie.id];
  video.currentTime=resume && h ? Math.min(h.position,video.duration) : 0;
  choosingResume=false; $('#resume-prompt').hidden=true; saveProgress(true); startVideo();
}
$('#resume-yes').addEventListener('click',()=>chooseResume(true));
$('#resume-no').addEventListener('click',()=>chooseResume(false));
async function saveProgress(force=false) {
  if(!currentMovie || !state.user || choosingResume || playerControls.switchingQuality || !Number.isFinite(video.duration) || video.duration<=0)return;
  if(!force && Date.now()-lastSave<5000)return;
  lastSave=Date.now();
  const id=currentMovie.id, position=Math.min(video.currentTime,video.duration), duration=video.duration;
  const record={position,duration,completed:position/duration>=.95,updatedAt:new Date().toISOString()};
  state.user.history[id]=record;
  const owner=state.user.id;
  progressQueue=progressQueue.then(async()=>{
    if(state.user?.id!==owner)return;
    try{await api('progress',{id,position,duration},{keepalive:true});}
    catch(error){toast(`İzleme konumu kaydedilemedi: ${error.message}`);}
  });
  await progressQueue;
}
video.addEventListener('timeupdate',()=>{if(!video.paused)saveProgress();});
video.addEventListener('pause',()=>saveProgress(true));
video.addEventListener('seeked',()=>saveProgress(true));
video.addEventListener('ended',()=>saveProgress(true));
video.addEventListener('error',()=>{if(playerControls.handleError())return;if(currentMovie)$('#player-error').textContent=currentMovie.demo?'Örnek video yüklenemedi. İnternet bağlantını kontrol edip içeriği yeniden aç.':'Video oynatılamadı. Oturumunu ve dosyanın H.264/AAC uyumunu kontrol edip içeriği yeniden aç.';});
$('#player-close').addEventListener('click',()=>$('#player-dialog').close());
$('#player-dialog').addEventListener('close',async()=>{
  clearTimeout(resumeTimer); video.pause();
  const saving = saveProgress(true);
  currentMovie=null; choosingResume=false; video.removeAttribute('src'); video.load();
  playerControls.close();if(document.fullscreenElement && $('#player-dialog').contains(document.fullscreenElement))document.exitFullscreen().catch(()=>{});
  $('#resume-prompt').hidden=true; render();
  await saving;
  try { if(!currentMovie){await refreshMe(); if(!currentMovie)render();} } catch(error){toast(error.message);}
});
document.addEventListener('visibilitychange',()=>{if(document.hidden)saveProgress(true);});
window.addEventListener('pagehide',()=>saveProgress(true));

let uploading = false;
let stagedVideo = null, stagedCover = null;
let stagedQuality = null;
function renderAdmin() {
  const allowed=state.user?.role==='admin';
  $('#admin-workspace').hidden=!allowed; $('#admin-access').hidden=allowed;
  if(!allowed) {
    $('#admin-access').innerHTML=empty('Bu alan yöneticilere ayrıldı.',state.user?'İçerik eklemek için yönetici hesabınla giriş yap.':'Yönetici hesabınla giriş yaparak içerik yükleyebilirsin.',state.user?'':'<button class="button primary" data-auth>Giriş yap →</button>');
    return;
  }
  refreshMailStatus();
  const published=state.movies.filter(movie=>!movie.demo);
  const oldChoice=$('#quality-movie').value;
  $('#quality-movie').replaceChildren(...published.map(movie=>{const option=document.createElement('option');option.value=movie.id;option.textContent=movie.title;return option;}));
  if(published.some(movie=>movie.id===oldChoice))$('#quality-movie').value=oldChoice;
  $('#quality-fields').disabled=!published.length||uploading;
  $('#admin-library').innerHTML=published.length?`<div class="card-grid">${published.map(card).join('')}</div>`:empty('İlk içeriğini sen ekle.','Yayınladığın videolar burada ve ana sayfada görünecek.');
}
async function refreshMailStatus(){
  if(state.user?.role!=='admin')return;
  const target=$('#mail-status-summary');
  try{
    const status=await api('admin/mail-status');
    target.textContent=`${status.safeMessage} Bekleyen: ${status.queued}. E-posta sunucusuna iletilen: ${status.sent}.`;
  }catch(error){target.textContent=error.status===404?'Sunucuyu güncel sürümle yeniden başlatıp tekrar dene.':error.message;}
}
$('#mail-status-refresh').addEventListener('click',refreshMailStatus);
function uploadFile(file, kind, label, onProgress=null) {
  return new Promise((resolve,reject)=>{
    const request=new XMLHttpRequest();
    request.open('POST',`/api/admin/uploads?kind=${kind}`);
    request.setRequestHeader('Content-Type',file.type || 'application/octet-stream');
    const report=(percent)=>{if(onProgress)onProgress(percent);else{$('#upload-progress').value=percent;$('#upload-status-text').textContent=percent===100?`${label} kaydediliyor…`:`${label} yükleniyor · %${percent}`;}};
    report(0);
    request.upload.addEventListener('progress',event=>{
      if(event.lengthComputable){
        const percent=Math.round(event.loaded/event.total*100);
        report(percent);
      }
    });
    request.addEventListener('load',()=>{
      try { const data=JSON.parse(request.responseText); if(request.status<200 || request.status>=300)throw new Error(data.error || 'Yükleme tamamlanamadı.'); resolve(data.asset); }
      catch(error){reject(error);}
    });
    request.addEventListener('error',()=>reject(new Error('Sunucuya ulaşılamadı. Bağlantını kontrol edip tekrar dene.')));
    request.addEventListener('abort',()=>reject(new Error('Yükleme iptal edildi.')));
    request.send(file);
  });
}
$('#upload-form').addEventListener('submit',async event=>{
  event.preventDefault(); if(uploading)return;
  const form=event.currentTarget;
  const file=form.elements.video.files[0], cover=form.elements.cover.files[0];
  $('#upload-error').textContent='';
  if(!file || !file.size || file.size>2*1024**3){$('#upload-error').textContent='Boş olmayan, en fazla 2 GB bir MP4 dosyası seç.';return;}
  if(cover && (!cover.size || cover.size>10*1024**2)){$('#upload-error').textContent='Kapak görseli boş olamaz ve 10 MB değerini aşamaz.';return;}
  const metadata={title:form.elements.title.value.trim(),description:form.elements.description.value.trim(),genre:form.elements.genre.value,type:form.elements.type.value,year:Number(form.elements.year.value)};
  uploading=true; $('#upload-fields').disabled=true; $('#upload-status').hidden=false;
  try {
    if(!stagedVideo || stagedVideo.file!==file)stagedVideo={file,asset:await uploadFile(file,'video','Video')};
    if(cover && (!stagedCover || stagedCover.file!==cover))stagedCover={file:cover,asset:await uploadFile(cover,'cover','Kapak')};
    $('#upload-status-text').textContent='İçerik yayınlanıyor…';
    await api('admin/content',{...metadata,videoId:stagedVideo.asset.id,coverId:cover?stagedCover.asset.id:null});
    stagedVideo=null; stagedCover=null; form.reset();
    state.movies=(await api('catalog')).movies; await refreshMe();
    $('#upload-progress').value=100; $('#upload-status-text').textContent='Yayınlandı! İçeriğin aşağıda ve ana sayfada izlenmeye hazır.';
    render(); toast('İçeriğin yayınlandı. İyi seyirler!');
  } catch(error){$('#upload-error').textContent=error.message;$('#upload-status-text').textContent='İşlem tamamlanamadı. Bilgileri kontrol edip tekrar deneyebilirsin.';}
  finally{uploading=false;$('#upload-fields').disabled=false;if(state.view==='admin')renderAdmin();}
});
$('#quality-form').addEventListener('submit',async event=>{
  event.preventDefault();if(uploading)return;
  const form=event.currentTarget;const file=form.elements.video.files[0];
  const id=form.elements.movieId.value,quality=form.elements.quality.value;
  $('#quality-upload-error').textContent='';
  if(!file || !file.size || file.size>2*1024**3){$('#quality-upload-error').textContent='En fazla 2 GB olan bir MP4 dosyası seç.';return;}
  if(!id){$('#quality-upload-error').textContent='Önce bir içerik yayınla.';return;}
  uploading=true;$('#quality-fields').disabled=true;$('#upload-fields').disabled=true;
  try{
    if(!stagedQuality || stagedQuality.file!==file)stagedQuality={file,asset:await uploadFile(file,'video',quality,percent=>$('#quality-upload-status').textContent=`${quality} yükleniyor · %${percent}`)};
    await api('admin/qualities',{id,assetId:stagedQuality.asset.id,quality});
    stagedQuality=null;form.reset();state.movies=(await api('catalog')).movies;
    $('#quality-upload-status').textContent='Kalite sürümü eklendi. Oynatıcıdaki ayarlardan seçilebilir.';toast('Yeni kalite sürümü hazır.');
  }catch(error){$('#quality-upload-error').textContent=error.message;$('#quality-upload-status').textContent='İşlem tamamlanamadı.';}
  finally{uploading=false;$('#upload-fields').disabled=false;renderAdmin();}
});
window.addEventListener('beforeunload',event=>{if(uploading){event.preventDefault();event.returnValue='';}});

async function init() {
  try {
    state.movies=(await api('catalog')).movies;
    await checkServerVersion();
    try {const data=await api('me');state.user=data.user;state.recommendations=data.recommendations;}catch(error){if(!error.message.includes('giriş yapın'))toast(error.message);}
    updateProfile(); navigate(location.hash.slice(1)||'home');
  } catch(error) { $('#content').innerHTML=empty('Bağlantı kurulamadı.','Python sunucusunun çalıştığından emin ol ve sayfayı yenile.'); toast(error.message); }
}
init();
