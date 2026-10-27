/* Shared, framework-independent prototype review. No page-specific selectors. */
(() => {
  'use strict';
  if (window.PrototypeReview) return;
  const script = document.currentScript;
  const assets = new URL('.', script.src);
  const endpoint = script.dataset.endpoint || '';
  const shared = script.dataset.shared === 'true';
  const codexEnabled = script.dataset.codex === 'true' && !shared;
  const basePath = script.dataset.basePath || '/';
  const attributeJSON = name => {
    try { return JSON.parse(script.dataset[name] || '{}'); } catch { return {}; }
  };
  const projectId = script.dataset.projectId || '';
  const pageIdentity = {strategy:'pathname',queryKeys:[],includeHash:false,...attributeJSON('pageIdentity')};
  const browserStorage = {namespace:projectId,legacyKeys:[],...attributeJSON('browserStorage')};
  const namespace = browserStorage.namespace || projectId;
  const storageKeys = Object.fromEntries(['comments','codexDrafts','codexRequests'].map(kind=>[
    kind,namespace?'prototype.review.'+encodeURIComponent(namespace)+'.'+kind:
      kind==='comments'?'prototype.review.v1':'prototype.review.'+kind
  ]));
  const readStorage = (storage,kind,fallback) => {
    try {
      const target=storageKeys[kind],legacy=kind==='comments'?'prototype.review.v1':'prototype.review.'+kind;
      // Only named legacy keys may be read, and never overwrite or remove evidence.
      if(namespace&&Array.isArray(browserStorage.legacyKeys)&&browserStorage.legacyKeys.includes(legacy)){
        const marker=target+'.migrated.'+encodeURIComponent(legacy);
        if(storage.getItem(target)===null&&storage.getItem(marker)===null){
          const original=storage.getItem(legacy);
          if(original!==null){
            JSON.parse(original);
            storage.setItem(target,original);
            storage.setItem(marker,JSON.stringify({source:legacy,target,copiedAt:new Date().toISOString()}));
          }
        }
      }
      return JSON.parse(storage.getItem(target)||fallback);
    } catch { return JSON.parse(fallback); }
  };
  const pageKey = value => {
    const url = new URL(value || '/',location.href);
    let path = url.pathname;
    if(basePath !== '/' && path.startsWith(basePath))path = '/' + path.slice(basePath.length);
    path=path.replace(/\/index\.html$/, '/');
    const query=new URLSearchParams();
    const keys=Array.isArray(pageIdentity.queryKeys)?pageIdentity.queryKeys:[];
    [...new Set(keys)].sort().forEach(key=>url.searchParams.getAll(key).forEach(value=>query.append(key,value)));
    return path+(query.size?'?'+query.toString():'')+(pageIdentity.includeHash?url.hash:'');
  };
  const storageKey = storageKeys.comments;
  const fileMode = location.protocol === 'file:';
  const imageTypes=['image/png','image/jpeg','image/webp','image/gif'];
  const maxImages=6,maxImageBytes=5*1024*1024,maxTotalImageBytes=10*1024*1024;
  let delegate = null;
  const events=['pointerdown','pointermove','pointerup','pointercancel','mousedown','mousemove','mouseup','click','dblclick','auxclick','contextmenu','touchstart','touchmove','touchend','dragstart','dragover','drop','keydown','keyup','keypress','beforeinput','input','change','paste','submit','focusin','focusout','wheel'];
  // Register before application window listeners; mount the UI once DOM is ready.
  events.forEach(type=>window.addEventListener(type,e=>delegate?.(e),{capture:true,passive:false}));
  const ready = () => {
    const host = document.createElement('div');
    host.id = 'prototype-review';
    host.dataset.html2canvasIgnore = 'true';
    host.style.cssText = 'position:fixed;inset:0;z-index:2147483647;pointer-events:none;';
    const ui = host.attachShadow({mode: 'open'});
    ui.innerHTML = `<link rel="stylesheet" href="${new URL('review.css', assets)}"><div id="toolbar"></div><div id="outline"></div><div id="markers"></div><div id="editor"></div><div id="list"></div><div id="codex-panel"></div><div id="notice" role="status" aria-live="polite"></div>`;
    document.documentElement.append(host);
    const pageStyle = document.createElement('style');
    pageStyle.textContent = 'html[data-prototype-review-active] body *{cursor:crosshair!important}html[data-prototype-review-active] svg path,html[data-prototype-review-active] svg line,html[data-prototype-review-active] svg polyline{pointer-events:visiblePainted!important}';
    document.head.append(pageStyle);
    const $ = id => ui.getElementById(id);
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const unique = selector => { try { return document.querySelectorAll(selector).length === 1; } catch { return false; } };
    const query = selector => { try { return document.querySelector(selector); } catch { return null; } };
    const state = {active:false, mode:'element', selected:null, hover:null, drag:null, note:'', attachments:[], adding:false, items:[], list:false, all:false, saving:false, error:'', build:'local', animations:[], videos:[], editing:null, childStack:[], codex:null, codexAvailable:false, codexReason:'正在连接本机 Codex', codexPanel:false, codexSending:false, chatSending:false, chatError:'', chatDrafts:{}, chatRequests:{}};
    try{state.chatDrafts=readStorage(sessionStorage,'codexDrafts','{}');}catch{}
    try{state.chatRequests=readStorage(sessionStorage,'codexRequests','{}');}catch{}
    let shotPromise = null, screenshot = null, libraryPromise = null, noticeTimer, listFocus = null, toolbarMarkup = '';

    function label(el) {
      return (el.getAttribute('aria-label') || el.getAttribute('alt') || el.getAttribute('placeholder') || (el.innerText || el.textContent || '').trim().replace(/\s+/g,' ') || el.id || el.tagName.toLowerCase()).slice(0,100);
    }
    function path(el) {
      if (el === document.documentElement) return 'html';
      const parts = [];
      while (el && el.nodeType === 1) {
        let base = el.tagName.toLowerCase();
        if (el.id && unique('#' + CSS.escape(el.id))) { parts.unshift('#' + CSS.escape(el.id)); break; }
        // Stable identifiers are optional; any page can supply them without an adapter.
        const attrs = [...el.attributes].filter(a => /^data-(review-id|testid|node|edge|id|key)$/.test(a.name));
        for (const attr of attrs) {
          const candidate = base + '[' + attr.name + '="' + CSS.escape(attr.value) + '"]';
          if (unique(candidate)) { parts.unshift(candidate); return parts.join(' > '); }
        }
        const cls = [...el.classList].filter(c => !/^(active|selected|open|hover|focused|running|complete|paused)$/.test(c)).slice(0,2);
        if (cls.length) base += cls.map(c => '.' + CSS.escape(c)).join('');
        const siblings = el.parentElement ? [...el.parentElement.children].filter(e => e.tagName === el.tagName) : [];
        if (siblings.length > 1) base += ':nth-of-type(' + (siblings.indexOf(el) + 1) + ')';
        parts.unshift(base);
        if (unique(parts.join(' > '))) break;
        el = el.parentElement;
      }
      return parts.join(' > ');
    }
    function rect(r) { return {x:r.x,y:r.y,width:r.width,height:r.height}; }
    function hit(x,y) {
      let el = document.elementsFromPoint(x,y).find(e => e !== host && !host.contains(e));
      if (!el) return document.body;
      if (el.tagName.toLowerCase() === 'path' && el.closest('button,a')) el = el.closest('button,a');
      return el;
    }
    function anchor(el, r, kind, selectedText='') {
      const bounds = el.getBoundingClientRect();
      const ancestors = [];
      for (let e=el; e && ancestors.length<10; e=e.parentElement) {
        ancestors.push({selector:path(e),tag:e.tagName,label:label(e),attributes:Object.fromEntries([...e.attributes].filter(a=>a.name.startsWith('data-') || a.name==='aria-label').map(a=>[a.name,a.value])),transform:getComputedStyle(e).transform});
      }
      return {kind,selector:path(el),tag:el.tagName,label:kind==='area'?`框选区域 · ${Math.round(r.width)} × ${Math.round(r.height)}`:label(el),selectedText,fingerprint:label(el),rect:r,
        relative:{x:(r.x-bounds.x)/(bounds.width||1),y:(r.y-bounds.y)/(bounds.height||1),width:r.width/(bounds.width||1),height:r.height/(bounds.height||1)},
        documentRect:{...r,x:r.x+scrollX,y:r.y+scrollY},ancestors,html:el.outerHTML.slice(0,12000)};
    }
    function pageContext() {
      return {path:pageKey(location.href),url:location.href,title:document.title,build:state.build,
        viewport:{width:innerWidth,height:innerHeight,devicePixelRatio},scroll:{x:scrollX,y:scrollY},
        capturedAt:new Date().toISOString(),
        dialogs:[...document.querySelectorAll('[role=dialog],dialog[open]')].map(el=>({selector:path(el),label:label(el)})),
        appearance:[document.documentElement,document.body,...document.querySelectorAll('[data-theme],[data-look]')].slice(0,8).map(el=>({selector:path(el),data:{...el.dataset}}))};
    }
    function notice(message) { $('notice').textContent=message; clearTimeout(noticeTimer); noticeTimer=setTimeout(()=>$('notice').textContent='',4500); }
    function toolbar() {
      const n=state.items.filter(c=>c.status!=='resolved').length;
      const markup = `<div class="bar ${state.active?'active':''}"><button data-action="move-toolbar" class="grip" aria-label="拖动评论工具栏" title="拖动工具栏">⠿</button>${state.active?`<strong><i></i>评论中</strong><div class="modes" aria-label="选区方式">${[['element','点选'],['area','框选'],['text','文字']].map(([v,t])=>`<button data-action="mode" data-mode="${v}" aria-pressed="${state.mode===v}">${t}</button>`).join('')}</div><button data-action="toggle" class="exit">退出评论</button>`:'<button data-action="toggle" class="enter">评论模式</button>'}<button data-action="list" aria-expanded="${state.list}">评论 <span class="count">${n}</span></button>${codexEnabled?codexButton():''}</div>${state.active?`<div class="hint">${state.mode==='text'?'拖选文字后添加评论':'点选元素，拖动可框选任意区域'} · Esc 取消选区</div>`:''}`;
      // Focus and polling refreshes must not replace a button between pointerdown and click.
      if(markup!==toolbarMarkup){toolbarMarkup=markup;$('toolbar').innerHTML=markup;}
      positionCodex();
    }
    function pendingComments() {return state.items.filter(c=>c.status==='open').sort((a,b)=>a.number-b.number);}
    function batchComments(job=state.codex) {return job?.comments||(job?.comment?[job.comment]:[]);}
    function sameBatch(comments,job=state.codex) {
      const previous=batchComments(job);
      return !!job&&comments.length===previous.length&&comments.every(c=>previous.some(p=>p.id===c.id&&p.updatedAt===c.updatedAt));
    }
    function codexBusy() {return ['starting','running','stopping'].includes(state.codex?.status);}
    function unsavedReview() {
      return !!state.selected&&(!state.editing||state.note!==state.editing.text||JSON.stringify(state.attachments)!==JSON.stringify(state.editing.attachments||[]));
    }
    function codexButton() {
      const pending=pendingComments(),job=state.codex,busy=codexBusy();
      const canStart=pending.length>0&&!sameBatch(pending)&&!busy;
      const blocked=state.codexSending||(canStart&&(unsavedReview()||!state.codexAvailable))||(!job&&(!canStart||!state.codexAvailable));
      const title=canStart&&unsavedReview()?'请先保存当前评论':busy?'查看进度或补充要求':canStart?`处理全部 ${pending.length} 条待处理评论（所有页面）`:job?'查看结果或继续对话':state.codexReason||'暂无待处理评论';
      const ended={completed:'已完成',failed:'未完成',cancelled:'已停止'}[job?.status]||'查看任务';
      return `<button class="codex-launch ${busy?'running':''}" data-action="codex" title="${esc(title)}" aria-expanded="${state.codexPanel}" aria-controls="codex-panel" ${blocked?'disabled':''}>${busy?'<i aria-hidden="true"></i>':''}${busy?`Codex 处理中 ${job.completedCount||0}/${batchComments().length}`:canStart?`交给 Codex · ${pending.length}`:job?`${ended} · 查看结果`:'交给 Codex'}</button>${job&&canStart?`<button class="codex-history" data-action="codex-details" aria-label="继续当前任务对话" title="查看上次任务与对话" aria-expanded="${state.codexPanel}">⌃</button>`:''}`;
    }
    function positionCodex() {
      const panel=$('codex-panel');if(!state.codexPanel||!panel.firstChild)return;
      const bar=$('toolbar').getBoundingClientRect(),width=Math.min(440,innerWidth-24);
      const above=bar.top-20,below=innerHeight-bar.bottom-20,up=above>=Math.min(420,below);
      panel.style.width=width+'px';panel.style.left=Math.max(12,Math.min(innerWidth-width-12,bar.left+bar.width/2-width/2))+'px';
      panel.style.maxHeight=Math.max(80,up?above:below)+'px';
      panel.style.top=up?'auto':bar.bottom+8+'px';panel.style.bottom=up?innerHeight-bar.top+8+'px':'auto';
      panel.dataset.side=up?'above':'below';
    }
    function showCodex(open,focus=false) {
      state.codexPanel=open;
      if(open){state.list=false;renderList();}
      renderCodex();toolbar();
      if(focus&&open)$('codex-input')?.focus();
    }
    function storeChatDraft(value) {
      if(!state.codex)return;
      state.chatDrafts[state.codex.id]=value;
      try{sessionStorage.setItem(storageKeys.codexDrafts,JSON.stringify(state.chatDrafts));}catch{}
    }
    function updateChatSend() {
      const send=ui.querySelector('[data-action="codex-send"]');
      if(send)send.disabled=state.chatSending||!$('codex-input')?.value.trim()||!state.codex?.canChat||state.codex?.status==='stopping'||!state.codexAvailable;
    }
    function renderCodex() {
      const panel=$('codex-panel');
      $('editor').hidden=state.codexPanel;
      if(!state.codexPanel){panel.innerHTML='';return;}
      const job=state.codex,busy=codexBusy(),comments=batchComments(),remaining=job?.pendingCount??comments.length;
      if(!job)return;
      const status={starting:'正在启动',running:'正在处理',stopping:'正在停止',completed:'本轮已完成',failed:'未完成',cancelled:'已停止'}[job.status]||'连接中';
      const labels={open:'待处理',changed:'待验收',resolved:'已解决',unknown:'状态待核对'};
      // Keep the composer and its IME, selection, focus, and draft intact during polling.
      if(panel.firstElementChild?.dataset.job!==job.id){
        panel.innerHTML=`<section class="panel codex-task" data-job="${esc(job.id)}" role="dialog" aria-label="Codex 评论任务"><header><div><small>本机 Codex · 评论任务</small><strong id="codex-title"></strong></div><button data-action="codex-close" aria-label="收起 Codex 任务" title="收起，任务继续运行">⌄</button></header><div id="codex-state"></div><div id="codex-thread" class="codex-thread" role="log" aria-label="任务对话"></div><details class="codex-records"><summary>本批评论 <span>${comments.length}</span></summary><ol class="codex-comments"></ol></details><div class="codex-compose"><label class="sr-only" for="codex-input">给当前 Codex 任务发消息</label><textarea id="codex-input" rows="2" maxlength="4000" placeholder="补充要求，或询问当前进度…"></textarea><div class="codex-compose-actions"><small>发送到同一任务 · ⌘ / Ctrl + Enter</small><button class="primary" data-action="codex-send">发送 ↑</button></div><p id="codex-chat-error" class="error" role="status"></p></div><footer id="codex-footer"></footer></section>`;
        $('codex-input').value=state.chatDrafts[job.id]||'';
      }
      $('codex-title').textContent=`${status} · ${comments.length} 条评论`;
      const setMarkup=(el,markup)=>{if(el.innerHTML!==markup)el.innerHTML=markup;};
      setMarkup($('codex-state'),`<div class="codex-summary">已处理 ${job.completedCount||0}/${comments.length} 条${remaining?` · 未完成 ${remaining} 条`:''}</div><p class="codex-progress ${job.error?'error':''}" title="${esc(job.error||job.progress)}">${esc(job.error||job.progress)}</p>`);
      setMarkup(ui.querySelector('.codex-comments'),comments.map(c=>`<li><span title="${esc(c.text)}">#${c.number} ${esc(c.text||'图片评论')}</span><small>${labels[c.reviewStatus]||'待处理'}</small></li>`).join(''));
      const messages=job.messages?.length?job.messages:job.result?[{id:'result',role:'assistant',text:job.result}]:[];
      const log=$('codex-thread'),nearEnd=log.scrollHeight-log.scrollTop-log.clientHeight<40;
      const messageMarkup=messages.filter(m=>m.text).map(m=>`<article class="codex-message ${m.role==='user'?'from-user':'from-agent'}"><div class="codex-message-meta"><small>${m.role==='user'?'你':'Codex'}</small>${m.role==='user'?`<small class="${m.status==='failed'?'error':''}">${esc(m.status==='queued'?'待送达':m.status==='failed'?m.error||'未送达':'已送达')}</small>`:''}</div><p>${esc(m.text)}</p></article>`).join('')||'<p class="codex-welcome">可以在这里补充要求，或随时询问进度。</p>';
      setMarkup(log,messageMarkup);if(nearEnd)log.scrollTop=log.scrollHeight;
      $('codex-chat-error').textContent=state.chatError;
      $('codex-input').disabled=!job.canChat||job.status==='stopping';
      setMarkup($('codex-footer'),`<span>${busy?'新评论留到下一批':'修改结果仍需你验收'}</span><div>${busy?`<button data-action="codex-stop" ${job.status==='stopping'?'disabled':''}>停止任务</button>`:`${remaining?`<button data-action="codex-retry" data-id="${esc(job.id)}">重试未完成</button>`:''}<button data-action="codex-reload">刷新原型</button>`}</div>`);
      updateChatSend();positionCodex();
    }
    async function syncCodex() {
      if(!codexEnabled)return;
      try{
        const response=await fetch(endpoint+'codex');if(!response.ok)throw Error('本机任务服务不可用');
        const data=await response.json(),previous=state.codex?.status;
        const changed=JSON.stringify(state.codex)!==JSON.stringify(data.job)||state.codexAvailable!==data.available||state.codexReason!==data.reason;
        state.codex=data.job;state.codexAvailable=data.available;state.codexReason=data.reason;
        if(changed){toolbar();renderCodex();}
        const stale=batchComments().some(c=>state.items.some(item=>item.id===c.id&&item.status!==c.reviewStatus));
        if(stale||(previous&&previous!==data.job?.status&&!codexBusy()))await refresh();
      }catch(error){state.codexAvailable=false;state.codexReason=error.message;toolbar();updateChatSend();}
    }
    async function startCodex(retryJobId) {
      if(state.codexSending)return;
      if(codexBusy()){showCodex(!state.codexPanel);return;}
      if(unsavedReview()){if(state.codex&&!retryJobId)showCodex(!state.codexPanel);else notice('请先保存当前评论，再交给 Codex');return;}
      state.codexSending=true;toolbar();
      try{
        await refresh();
        const pending=pendingComments();
        if(!retryJobId&&(!pending.length||sameBatch(pending))){showCodex(!state.codexPanel&&!!state.codex);if(!state.codex)notice('暂无待处理评论');return;}
        const response=await fetch(endpoint+'codex',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(retryJobId?{retryJobId}:{scope:'all-open'})});
        const data=await response.json();if(!response.ok)throw Error(data.error||'任务未启动');
        state.codex=data.job;state.chatError='';showCodex(!!retryJobId);
        if(!retryJobId)notice('Codex 已开始处理，点击工具栏进度可补充要求');
      }finally{state.codexSending=false;toolbar();}
    }
    async function sendCodexMessage() {
      const field=$('codex-input'),job=state.codex,text=field?.value.trim();
      if(!text||state.chatSending||!job?.canChat||job.status==='stopping')return;
      const previous=state.chatRequests[job.id];
      const messageId=previous?.text===text?previous.id:crypto.randomUUID().replaceAll('-','');
      state.chatRequests[job.id]={id:messageId,text};state.chatSending=true;state.chatError='';updateChatSend();
      try{sessionStorage.setItem(storageKeys.codexRequests,JSON.stringify(state.chatRequests));}catch{}
      try{
        const response=await fetch(endpoint+'codex/message',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({jobId:job.id,messageId,text})});
        const data=await response.json();if(!response.ok)throw Error(data.error||'消息未发送，请重试');
        if(state.codex?.id===job.id){
          state.codex=data.job;
          if((state.chatDrafts[job.id]||'').trim()===text){storeChatDraft('');if($('codex-input'))$('codex-input').value='';}
        }
        delete state.chatRequests[job.id];
        try{sessionStorage.setItem(storageKeys.codexRequests,JSON.stringify(state.chatRequests));}catch{}
      }catch(error){state.chatError=error.message;}
      finally{state.chatSending=false;renderCodex();toolbar();}
    }
    function setActive(active) {
      state.active=active; state.hover=null; state.drag=null;
      document.documentElement.toggleAttribute('data-prototype-review-active',active);
      if (active) {
        if(fileMode)notice('离线文件保存评论与选区；本机评审入口可同时保存截图');
        state.animations=document.getAnimations().filter(a=>a.playState==='running');
        state.animations.forEach(a=>a.pause());
        state.videos=[...document.querySelectorAll('video')].filter(v=>!v.paused);
        state.videos.forEach(v=>v.pause());
      } else {
        state.animations.forEach(a=>{try{a.play()}catch{}}); state.animations=[];
        state.videos.forEach(v=>v.play().catch(()=>{})); state.videos=[];
        cancelSelection();
      }
      toolbar(); draw();
    }
    function cancelSelection() {
      state.selected=null;state.editing=null;state.note='';state.attachments=[];state.adding=false;state.error='';state.childStack=[];
      shotPromise=null;screenshot=null;getSelection()?.removeAllRanges();editor();draw();
    }
    async function capture() {
      if (!window.html2canvas) {
        if (!libraryPromise) libraryPromise=new Promise((resolve,reject)=>{
          const el=document.createElement('script');el.src=new URL('html2canvas.min.js',assets);el.onload=resolve;el.onerror=()=>{libraryPromise=null;el.remove();reject(Error('截图工具加载失败，请重试'));};document.head.append(el);
        });
        await libraryPromise;
      }
      const canvas=await window.html2canvas(document.body,{width:innerWidth,height:innerHeight,x:scrollX,y:scrollY,scrollX,scrollY,scale:1,logging:false,imageTimeout:3000,useCORS:true,
        ignoreElements:el=>el===host || el.id==='prototype-review',
        onclone:doc=>{doc.getElementById('prototype-review')?.remove();doc.querySelectorAll('script').forEach(e=>e.remove());}});
      return canvas.toDataURL('image/png');
    }
    async function markSnapshot(data,r) {
      const image=new Image();image.src=data;await image.decode();
      const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;
      const context=canvas.getContext('2d');context.drawImage(image,0,0);
      context.strokeStyle='#b9a3ff';context.lineWidth=3;context.fillStyle='#b9a3ff16';
      context.fillRect(r.x,r.y,r.width,r.height);context.strokeRect(r.x,r.y,r.width,r.height);
      return canvas.toDataURL('image/png');
    }
    function select(el,r,kind,text='') {
      if(state.adding)return;
      state.selected={id:crypto.randomUUID?crypto.randomUUID():'review-'+Date.now()+'-'+Math.random().toString(16).slice(2),anchor:anchor(el,r,kind,text),page:pageContext(),element:el};state.editing=null;state.hover=null;state.error='';state.childStack=[];
      const selected=state.selected;
      screenshot=null;
      // Start before the note popup is displayed; capture the selected UI state.
      shotPromise=(fileMode?Promise.resolve(null):capture()).then(data=>{if(state.selected===selected)screenshot=data;return data;}).catch(error=>{if(state.selected===selected){state.error=error.message;editor();}return null;});
      editor();draw();
    }
    function imageSource(image){return image.dataUrl||image.url||'';}
    function imageMarkup(images,editing=false,commentId=''){
      if(!images?.length)return '';
      return `<div class="attachments ${editing?'attachment-drafts':''}" aria-label="评论附图">${images.map((image,index)=>`<div class="attachment"><button class="attachment-preview" data-action="preview-attachment" data-index="${index}" ${commentId?`data-id="${esc(commentId)}"`:''} aria-label="预览附图 ${index+1}" title="${esc(image.name)}"><img src="${esc(imageSource(image))}" alt="附图 ${index+1}"></button>${editing?`<button class="attachment-remove" data-action="remove-attachment" data-index="${index}" aria-label="移除附图 ${index+1}" ${state.saving||state.adding?'disabled':''}>×</button>`:''}</div>`).join('')}</div>`;
    }
    function fileData(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('图片读取失败，请重新粘贴'));reader.readAsDataURL(file);});}
    async function addImages(files){
      if(!state.selected||state.saving||state.adding)return;
      const selected=state.selected,field=$('note-input'),selection=[field?.selectionStart||0,field?.selectionEnd||0];
      try{
        if(state.attachments.length+files.length>maxImages)throw Error('每条评论最多添加 6 张图片');
        if(files.some(file=>!imageTypes.includes(file.type)))throw Error('支持粘贴 PNG、JPEG、WebP 和 GIF 图片');
        if(files.some(file=>file.size>maxImageBytes))throw Error('每张图片不能超过 5 MB');
        if(files.reduce((n,file)=>n+file.size,0)+state.attachments.reduce((n,image)=>n+image.size,0)>maxTotalImageBytes)throw Error('每条评论的图片合计不能超过 10 MB');
        state.adding=true;state.error='';editor();
        const images=await Promise.all(files.map(async(file,index)=>{
          const dataUrl=await fileData(file),image=new Image();image.src=dataUrl;
          try{await image.decode();}catch{throw Error('图片无法读取，请重新复制或选择图片');}
          return {id:crypto.randomUUID?crypto.randomUUID():'image-'+Date.now()+'-'+Math.random().toString(16).slice(2),name:(file.name||'粘贴图片 '+(index+1)).slice(0,120),mimeType:file.type,size:file.size,dataUrl};
        }));
        if(state.selected!==selected)return;
        state.attachments.push(...images);
      }catch(error){if(state.selected===selected)state.error=error.message;}
      finally{if(state.selected===selected){state.adding=false;editor();$('note-input')?.focus();$('note-input')?.setSelectionRange(...selection);}}
    }
    function editor() {
      toolbar();
      if (!state.selected) { $('editor').innerHTML=''; return; }
      const a=state.selected.anchor;
      const r=liveRect(a) || a.rect;
      const left=Math.max(12,Math.min(innerWidth-352,r.x+r.width+14 > innerWidth-352 ? r.x-350 : r.x+r.width+14));
      const compact=innerWidth<=600,top=compact?110:Math.max(90,Math.min(innerHeight-365,r.y));
      $('editor').style.cssText=`left:${left}px;top:${top}px;max-height:${Math.max(160,innerHeight-top-(compact?110:16))}px`;
      $('editor').innerHTML=`<section class="panel note" role="dialog" aria-label="区块评论"><header><div><small>${state.editing?'编辑评论 #'+state.editing.number:{element:'元素评论',area:'区域评论',text:'文字评论'}[a.kind]}</small><strong>${esc(a.label)}</strong></div><button data-action="cancel" aria-label="取消评论">×</button></header>${a.selectedText?`<blockquote>${esc(a.selectedText)}</blockquote>`:''}${a.kind==='element'&&!state.editing?`<div class="ancestry"><button data-action="parent" ${state.selected.element?.parentElement?'':'disabled'}>扩大到父级</button><button data-action="child" ${state.childStack.length?'':'disabled'}>缩回一级</button></div>`:''}<textarea id="note-input" aria-label="评论内容" placeholder="希望这里如何调整？也可以直接粘贴图片。" maxlength="10000">${esc(state.note)}</textarea><div class="attachment-controls"><button data-action="add-image" ${state.saving||state.adding||state.attachments.length>=maxImages?'disabled':''}>＋ 添加图片</button><span>${state.adding?'正在读取图片…':'支持粘贴图片 · 最多 6 张'}</span><input type="file" id="image-input" accept="image/png,image/jpeg,image/webp,image/gif" multiple hidden></div>${imageMarkup(state.attachments,true)}<p class="error" role="alert">${esc(state.error)}</p><footer><span>${endpoint?(shared?'保存后团队可见':'保存到本机评审记录'):'保存到浏览器，可导出'}</span><button class="primary" data-action="save" ${state.saving||state.adding?'disabled':''}>${state.saving?'正在保存…':state.adding?'正在读取图片…':'保存评论'}</button></footer></section>`;
    }
    function liveRect(a) {
      const el=query(a.selector);
      if (!el || !el.isConnected || (a.fingerprint && label(el)!==a.fingerprint)) return null;
      const b=el.getBoundingClientRect();
      const visibleLine=el instanceof SVGGeometryElement && (b.width || b.height);
      if ((!b.width || !b.height) && !visibleLine || getComputedStyle(el).visibility==='hidden') return null;
      if (a.kind==='element') return rect(b);
      const p=a.relative;
      return p?{x:b.x+p.x*b.width,y:b.y+p.y*b.height,width:p.width*b.width,height:p.height*b.height}:a.rect;
    }
    function draw() {
      let box=state.selected?liveRect(state.selected.anchor):state.hover?rect(state.hover.getBoundingClientRect()):null;
      if(state.drag?.box)box=state.drag.box;
      $('outline').style.cssText=box?`display:block;left:${box.x}px;top:${box.y}px;width:${Math.max(2,box.width)}px;height:${Math.max(2,box.height)}px;`:'display:none';
      const visible=state.active || state.list;
      $('markers').innerHTML=visible?state.items.filter(c=>pageKey(c.page.path)===pageKey(location.href)&&c.status!=='resolved').map(c=>{
        const r=liveRect(c.anchor); if(!r || r.x+r.width<0 || r.y+r.height<0 || r.x>innerWidth || r.y>innerHeight)return '';
        return `<button class="marker ${c.status==='changed'?'changed':''}" style="left:${Math.max(3,Math.min(innerWidth-30,r.x+r.width-12))}px;top:${Math.max(3,r.y-12)}px" data-action="locate" data-id="${esc(c.id)}" title="${esc(c.text)}" aria-label="查看评论 ${c.number}">${c.number}</button>`;
      }).join(''):'';
    }
    function renderList() {
      if(!state.list){$('list').innerHTML='';return;}
      const items=state.items.filter(c=>state.all||pageKey(c.page.path)===pageKey(location.href)).slice().reverse();
      $('list').innerHTML=`<section class="panel comments" role="dialog" aria-label="评论列表"><header><div><small>${endpoint?(shared?'团队评审':'本机评审'):'浏览器评审副本'}</small><strong>评论记录</strong></div><button data-action="list" aria-label="关闭评论列表">×</button></header><div class="list-tools"><button data-action="filter" aria-pressed="${!state.all}">${state.all?'全部页面':'当前页面'} ▾</button><button data-action="refresh">刷新</button><button data-action="export">导出</button></div><div class="comment-items">${items.length?items.map(c=>`<article id="comment-${esc(c.id)}" class="comment ${c.id===listFocus?'focused':''}"><div class="comment-head"><button data-action="locate" data-id="${esc(c.id)}">#${c.number} · ${esc(c.anchor.label)}</button><span>${{open:'待处理',changed:'待验收',resolved:'已解决'}[c.status]}</span></div><p>${esc(c.text)}</p>${imageMarkup(c.attachments,false,c.id)}<small>${esc(c.page.title)}${c.page.build!==state.build?' · 来自之前的原型版本':''}</small>${c.anchor.selectedText?`<blockquote>${esc(c.anchor.selectedText)}</blockquote>`:''}${c.resolution?`<p class="resolution">修改说明：${esc(c.resolution)}</p>`:''}<div class="comment-actions"><button data-action="snapshot" data-id="${esc(c.id)}">${c.screenshot||c.screenshotData?'查看截图':'未附截图'}</button><button data-action="edit" data-id="${esc(c.id)}">编辑</button><button data-action="status" data-id="${esc(c.id)}" data-status="${c.status==='resolved'?'open':'resolved'}">${c.status==='resolved'?'重新打开':'标为解决'}</button></div></article>`).join(''):'<div class="empty">还没有评论。<br>进入评论模式，选中需要调整的区域。</div>'}</div><div class="list-foot">${endpoint?(shared?'评论和截图共享保存 · 自动同步更新':'评论和截图保存在本机项目目录'):'评论保存在当前浏览器；导出后可交给我处理'}</div></section>`;
    }
    async function refresh() {
      try {
        if(endpoint){const r=await fetch(endpoint+'comments');if(!r.ok)throw Error('评审服务暂不可用');const d=await r.json();state.items=d.comments;state.build=d.build;}
        else state.items=readStorage(localStorage,'comments','[]');
        toolbar();renderList();draw();
      }catch(error){notice(error.message||'读取评论失败，请重试');}
    }
    async function persist(comment) {
      if(endpoint){
        let response;
        try{response=await fetch(endpoint+'comments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({comment,expectedUpdate:comment.updatedAt})});}
        catch{throw Error('未收到评审服务的保存确认，内容已保留，请稍后重试保存。');}
        const data=await response.json();if(!response.ok)throw Error(data.error||'保存失败，请重试');
        const i=state.items.findIndex(c=>c.id===comment.id);if(i>=0)state.items[i]=data.comment;else state.items.push(data.comment);
      }else{
        const copy=state.items.slice(),i=copy.findIndex(c=>c.id===comment.id);
        comment.number=i>=0?copy[i].number:Math.max(0,...copy.map(c=>c.number))+1;comment.updatedAt=Date.now();comment.createdAt ||= comment.updatedAt;
        if(i>=0)copy[i]=comment;else copy.push(comment);
        try{localStorage.setItem(storageKey,JSON.stringify(copy));}catch{throw Error('浏览器存储空间不足，请先导出已有评论，再使用本机评审入口');}
        state.items=copy;
      }
    }
    async function save() {
      if(state.saving||state.adding||!state.selected)return;
      if(!state.note.trim()&&!state.attachments.length){state.error='请填写评论或粘贴图片';editor();$('note-input')?.focus();return;}
      state.saving=true;state.error='';editor();
      try{
        let comment;
        if(state.editing)comment={...state.editing,text:state.note.trim()};
        else {
          const image=fileMode?null:(screenshot || await shotPromise || await capture());
          if(!image&&!fileMode)throw Error('截图未生成，请重试保存');
          comment={id:state.selected.id,text:state.note.trim(),status:'open',anchor:state.selected.anchor,page:state.selected.page,screenshotData:image?await markSnapshot(image,state.selected.anchor.rect):undefined,snapshotNote:fileMode?'离线文件评论，未附截图':undefined};
        }
        comment.attachments=state.attachments.map(image=>({...image}));
        await persist(comment);cancelSelection();state.list=true;state.codexPanel=false;renderCodex();notice('评论已保存');
      }catch(error){state.error=error.message||'保存失败，评论内容已保留';}
      finally{state.saving=false;editor();toolbar();renderList();draw();}
    }
    function locate(comment) {
      listFocus=comment.id;state.list=true;state.codexPanel=false;renderCodex();renderList();
      if(pageKey(comment.page.path)!==pageKey(location.href)){notice('这条评论在其他页面；可先查看截图，或退出评论后打开 '+comment.page.path);return;}
      const r=liveRect(comment.anchor);
      if(!r){notice('原区块已变化或尚未展开，请查看截图并重新打开对应内容');return;}
      query(comment.anchor.selector)?.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'});
      state.selected={anchor:comment.anchor,page:comment.page,element:query(comment.anchor.selector)};state.editing=comment;state.note=comment.text;state.attachments=(comment.attachments||[]).map(image=>({...image}));state.adding=false;state.error='';editor();draw();
    }
    async function action(name, button) {
      const comment=state.items.find(c=>c.id===button?.dataset.id);
      if(state.saving && !['list'].includes(name)||state.adding&&!['list','cancel'].includes(name))return;
      if(name==='codex')await startCodex();
      if(name==='codex-retry')await startCodex(button.dataset.id);
      if(name==='codex-close'){showCodex(false);ui.querySelector('[data-action=codex]')?.focus();}
      if(name==='codex-details')showCodex(!state.codexPanel);
      if(name==='codex-send')await sendCodexMessage();
      if(name==='codex-reload'){if(unsavedReview())notice('请先保存当前评论再刷新');else location.reload();}
      if(name==='codex-stop'&&state.codex){
        const response=await fetch(endpoint+'codex/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({jobId:state.codex.id})});
        const data=await response.json();if(!response.ok)throw Error(data.error||'停止任务失败');
        await syncCodex();
      }
      if(name==='toggle')setActive(!state.active);
      if(name==='cancel'){cancelSelection();toolbar();}
      if(name==='mode'){state.mode=button.dataset.mode;state.drag=null;toolbar();}
      if(name==='list'){state.list=!state.list;if(state.list){state.codexPanel=false;renderCodex();}renderList();toolbar();draw();}
      if(name==='filter'){state.all=!state.all;renderList();}
      if(name==='refresh')await refresh();
      if(name==='save')await save();
      if(name==='add-image')$('image-input')?.click();
      if(name==='remove-attachment'){state.attachments.splice(Number(button.dataset.index),1);state.error='';editor();$('note-input')?.focus();}
      if(name==='preview-attachment'){
        const image=(comment?comment.attachments:state.attachments)?.[Number(button.dataset.index)];
        if(image){const w=window.open('','_blank');if(w){w.document.title=image.name||'评论附图';const img=w.document.createElement('img');img.src=imageSource(image);img.alt=image.name||'评论附图';img.style.maxWidth='100%';w.document.body.append(img);}}
      }
      if(name==='parent'||name==='child'){
        const current=state.selected?.element;
        const target=name==='parent'?current?.parentElement:state.childStack.pop();
        if(target&&target!==host){if(name==='parent')state.childStack.push(current);state.selected={...state.selected,element:target,anchor:anchor(target,rect(target.getBoundingClientRect()),'element')};editor();draw();}
      }
      if(name==='locate'||name==='edit'){if(!state.active)setActive(true);locate(comment);}
      if(name==='snapshot'){
        if(!comment.screenshotData&&!comment.screenshot){notice('这条离线评论未附截图；本机评审入口可同时保存截图');return;}
        const w=window.open('','_blank');if(w){w.document.title='评论 #'+comment.number+' · 选区截图';const img=w.document.createElement('img');img.src=comment.screenshotData||comment.screenshot;img.style.maxWidth='100%';w.document.body.append(img);}
      }
      if(name==='status'){
        try{await persist({...comment,status:button.dataset.status});renderList();toolbar();draw();}catch(error){notice(error.message);}
      }
      if(name==='export'){
        const copy=await Promise.all(state.items.map(async c=>{
          const embedded=async url=>{const r=await fetch(url);if(!r.ok)throw Error('图片导出失败，请稍后重试');return fileData(await r.blob());};
          const attachments=await Promise.all((c.attachments||[]).map(async image=>({...image,dataUrl:image.dataUrl||await embedded(image.url)})));
          return {...c,attachments,...(c.screenshot&&!c.screenshotData?{screenshotData:await embedded(c.screenshot)}:{})};
        }));
        const blob=new Blob([JSON.stringify({format:'prototype-review',version:2,comments:copy},null,2)],{type:'application/json'});
        const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='原型评论-'+new Date().toISOString().slice(0,10)+'.json';
        // An internal download is allowed; ordinary page links remain intercepted.
        a.dataset.reviewExport='true';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),5000);
      }
    }
    function caret(x,y) {
      if(document.caretPositionFromPoint){const p=document.caretPositionFromPoint(x,y);if(p)return {node:p.offsetNode,offset:p.offset};}
      const r=document.caretRangeFromPoint?.(x,y);return r?{node:r.startContainer,offset:r.startOffset}:null;
    }
    function selectText(start,end) {
      if(!start||!end || start.node.getRootNode()!==document || end.node.getRootNode()!==document)return;
      try{getSelection().setBaseAndExtent(start.node,start.offset,end.node,end.offset);}catch{}
    }
    function handle(e) {
      const eventPath=e.composedPath();
      if(eventPath.some(el=>el?.dataset?.reviewExport))return;
      if(state.drag?.toolbar&&e.type==='pointermove'){
        e.preventDefault();e.stopImmediatePropagation();const d=state.drag;
        $('toolbar').style.cssText=`left:${Math.max(0,Math.min(innerWidth-$('toolbar').offsetWidth,d.left+e.clientX-d.x))}px;top:${Math.max(0,Math.min(innerHeight-90,d.top+e.clientY-d.y))}px;bottom:auto;transform:none;`;positionCodex();return;
      }
      if(state.drag?.toolbar&&e.type==='pointerup'){e.preventDefault();e.stopImmediatePropagation();state.drag=null;return;}
      const own=eventPath.includes(host);
      if(own){
        // Catch at window, before document-level outside-click and focus traps.
        e.stopImmediatePropagation();
        const button=eventPath.find(el=>el?.dataset?.action);
        if(e.type==='paste'&&state.selected&&!eventPath.includes($('codex-panel'))){
          const files=[...(e.clipboardData?.items||[])].filter(item=>item.kind==='file').map(item=>item.getAsFile()).filter(Boolean);
          if(files.length){
            e.preventDefault();
            const text=e.clipboardData.getData('text/plain'),field=eventPath[0];
            if(text&&field.id==='note-input'&&!state.saving&&!state.adding){field.setRangeText(text,field.selectionStart,field.selectionEnd,'end');state.note=field.value;}
            addImages(files);
          }
        }
        if(e.type==='change'&&eventPath[0].id==='image-input')addImages([...eventPath[0].files]);
        if(e.type==='click'&&button&&!button.disabled){e.preventDefault();action(button.dataset.action,button).catch(error=>notice(error.message));}
        if(e.type==='input'&&eventPath[0].id==='note-input'){
          state.note=eventPath[0].value;
          // Keep the editor, its focus and text selection intact while updating draft actions.
          toolbar();
        }
        if(e.type==='input'&&eventPath[0].id==='codex-input'){storeChatDraft(eventPath[0].value);updateChatSend();}
        if(e.type==='pointerdown'&&button?.dataset.action==='move-toolbar'){
          e.preventDefault();const b=$('toolbar').getBoundingClientRect();state.drag={toolbar:true,x:e.clientX,y:e.clientY,left:b.left,top:b.top};
        }
        if(e.type==='keydown'){
          if(state.saving){e.preventDefault();return;}
          if(e.key==='Escape'){e.preventDefault();if(state.codexPanel&&(!state.selected||eventPath.includes($('codex-panel')))){showCodex(false);ui.querySelector('[data-action=codex]')?.focus();}else if(state.selected)cancelSelection();else setActive(false);}
          if(e.key==='Enter'&&!e.isComposing&&(e.metaKey||e.ctrlKey)){e.preventDefault();if(eventPath[0].id==='codex-input')sendCodexMessage();else save();}
        }
        return;
      }
      if(e.type==='keydown'&&e.key==='Escape'&&state.codexPanel&&!state.selected){e.preventDefault();e.stopImmediatePropagation();showCodex(false);return;}
      if(e.type==='pointerdown'&&state.codexPanel)showCodex(false);
      if(!state.active)return;
      e.stopImmediatePropagation();
      if(e.type==='wheel')return; // Keep native scrolling; block application wheel handlers.
      const fieldTarget=e.target?.matches?.('textarea,input[type=text],input:not([type]),input[type=search],input[type=url],input[type=tel]')?e.target:null;
      if(e.cancelable)e.preventDefault();
      if(state.saving)return;
      if(e.type==='keydown'){
        if(e.key==='Escape'){if(state.selected)cancelSelection();else setActive(false);}
        if(e.key==='Tab'){$('toolbar').querySelector('button[data-action="toggle"]')?.focus();}
        return;
      }
      if(e.type==='pointerdown'&&e.button===0){
        const el=hit(e.clientX,e.clientY);state.drag={x:e.clientX,y:e.clientY,el,field:fieldTarget,caret:state.mode==='text'&&!fieldTarget?caret(e.clientX,e.clientY):null};
        if(state.mode==='text')getSelection()?.removeAllRanges();
      }
      if(e.type==='pointermove'){
        const d=state.drag;
        if(d){
          if(state.mode==='text'){if(!d.field)selectText(d.caret,caret(e.clientX,e.clientY));return;}
          if(Math.hypot(e.clientX-d.x,e.clientY-d.y)>5 || state.mode==='area')d.box={x:Math.min(d.x,e.clientX),y:Math.min(d.y,e.clientY),width:Math.abs(e.clientX-d.x),height:Math.abs(e.clientY-d.y)};
        }else if(!state.selected)state.hover=hit(e.clientX,e.clientY);
        draw();
      }
      if(e.type==='pointerup'&&state.drag){
        const d=state.drag;state.drag=null;
        if(state.mode==='text'){
          if(d.field){
            select(d.field,rect(d.field.getBoundingClientRect()),'element');
            notice('已选中整个输入字段，可在评论中引用需要修改的文字');
            return;
          }
          const sel=getSelection();
          if(sel?.rangeCount&&!sel.isCollapsed){const range=sel.getRangeAt(0),el=range.commonAncestorContainer.nodeType===1?range.commonAncestorContainer:range.commonAncestorContainer.parentElement;select(el,rect(range.getBoundingClientRect()),'text',sel.toString());}
          else notice('请拖选页面中的文字；输入字段也可使用点选或框选评论');
        }else if(d.box&&d.box.width>3&&d.box.height>3){
          let el=d.el;const end=hit(e.clientX,e.clientY);while(el.parentElement&&!el.contains(end))el=el.parentElement;
          select(el,d.box,'area');
        }else select(d.el,rect(d.el.getBoundingClientRect()),'element');
      }
      if(e.type==='pointercancel')state.drag=null;
    }
    delegate=handle;
    window.addEventListener('scroll',draw,true);
    window.addEventListener('resize',()=>{editor();draw();positionCodex();});
    new ResizeObserver(positionCodex).observe($('toolbar'));
    new ResizeObserver(positionCodex).observe($('codex-panel'));
    let drawing=false;
    new MutationObserver(()=>{if(drawing)return;drawing=true;requestAnimationFrame(()=>{drawing=false;draw();});}).observe(document.body,{subtree:true,attributes:true,childList:true,characterData:true});
    window.addEventListener('blur',()=>{state.drag=null;});
    window.PrototypeReview={version:1};
    toolbar();refresh();
    if(codexEnabled){
      let syncing=false;
      const sync=async()=>{if(syncing||document.hidden)return;syncing=true;try{await syncCodex();}finally{syncing=false;}};
      sync();setInterval(sync,1500);window.addEventListener('focus',()=>{refresh();sync();});
      document.addEventListener('visibilitychange',sync);
    }
    if(shared){
      const sync = () => {if(!document.hidden && !state.saving)refresh();};
      setInterval(sync,15000);
      window.addEventListener('focus',sync);
      document.addEventListener('visibilitychange',sync);
    }
  };
  if(document.body)ready();else document.addEventListener('DOMContentLoaded',ready,{once:true});
})();
