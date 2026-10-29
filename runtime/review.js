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
  const storageKeys = Object.fromEntries(['comments','codexDrafts','codexRequests','annotations','annotationDraft','annotationChats','annotationRequests','annotationReplyAgent','annotationView'].map(kind=>[
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
    host.style.cssText = 'position:fixed;inset:0;z-index:2147483647;pointer-events:none;visibility:hidden;';
    const ui = host.attachShadow({mode: 'open'});
    ui.innerHTML = `<link rel="stylesheet" href="${new URL('review.css', assets)}"><div id="toolbar"></div><div id="outline"></div><div id="markers"></div><div id="editor"></div><div id="list"></div><div id="codex-panel"></div><div id="annotation-highlights"></div><div id="annotation-selection"></div><div id="annotation-panel"></div><div id="notice" role="status" aria-live="polite"></div>`;
    // Shadow-root styles load asynchronously. Keep controls hidden until their
    // layout is available, including on failure; register before connecting the
    // host so a cached stylesheet cannot finish before this listener is attached.
    let stylesLoaded=false;
    const stylesReady=new Promise(resolve=>{
      const link=ui.querySelector('link');
      link.addEventListener('load',()=>{stylesLoaded=true;host.style.removeProperty('visibility');renderAnnotations();drawAnnotations();resolve(true);},{once:true});
      link.addEventListener('error',()=>resolve(false),{once:true});
    });
    document.documentElement.append(host);
    const pageStyle = document.createElement('style');
    pageStyle.textContent = 'html[data-prototype-review-active] body *{cursor:crosshair!important}html[data-prototype-review-active] svg path,html[data-prototype-review-active] svg line,html[data-prototype-review-active] svg polyline{pointer-events:visiblePainted!important}';
    document.head.append(pageStyle);
    const $ = id => ui.getElementById(id);
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const unique = selector => { try { return document.querySelectorAll(selector).length === 1; } catch { return false; } };
    const query = selector => { try { return document.querySelector(selector); } catch { return null; } };
    const state = {active:false, mode:'element', selected:null, hover:null, drag:null, note:'', attachments:[], adding:false, items:[], list:false, all:false, saving:false, error:'', build:'local', animations:[], videos:[], editing:null, childStack:[], codex:null, codexAvailable:false, codexReason:'正在连接本机 Codex', codexPanel:false, codexSending:false, chatSending:false, chatError:'', chatDrafts:{}, chatRequests:{}, historyOpen:false, historyData:null, historyJob:null, historyLoading:false, historyError:'', historyRequest:0, historyRevision:0};
    try{state.chatDrafts=readStorage(sessionStorage,'codexDrafts','{}');}catch{}
    try{state.chatRequests=readStorage(sessionStorage,'codexRequests','{}');}catch{}
    let shotPromise = null, screenshot = null, libraryPromise = null, noticeTimer, listFocus = null, toolbarMarkup = '';

    const annotationViewKey=page=>storageKeys.annotationView+'.'+encodeURIComponent(page);
    function readAnnotationView(page){try{const value=JSON.parse(sessionStorage.getItem(annotationViewKey(page)));return value?.version===1?value:null;}catch{return null;}}
    let savedAnnotationView=readAnnotationView(pageKey(location.href));
    const ann={filter:['open','all','resolved'].includes(savedAnnotationView?.filter)?savedAnnotationView.filter:'open',layout:'drawer',reserve:null,tail:null,expanded:savedAnnotationView?.expanded||{},replyAgent:readStorage(localStorage,'annotationReplyAgent','{}'),items:[],open:!!savedAnnotationView?.open,current:savedAnnotationView?.current||null,draftView:true,selection:null,draft:readStorage(localStorage,'annotationDraft','null'),chats:readStorage(localStorage,'annotationChats','{}'),requests:readStorage(localStorage,'annotationRequests','{}'),agent:{enabled:false,available:false,reason:endpoint?'正在连接 Agent':'离线模式仅保存批注，不会启动 Agent'},sending:false,adding:false,error:'',selectionTimer:null,shot:null,viewReady:false,loadedBuild:script.dataset.build||null,editVersions:new Map(),observedEdits:false,refreshPending:null,reloading:false,composing:false,externalValues:new WeakMap(),externalDirty:new Set()};
    const requestId=()=>{const bytes=new Uint8Array(16);crypto.getRandomValues(bytes);return [...bytes].map(n=>n.toString(16).padStart(2,'0')).join('');};
    ann.viewPage=pageKey(location.href);ann.viewEpoch=0;ann.restoringView=null;
    const annotationCardResize=new ResizeObserver(()=>{if(ann.open)requestAnimationFrame(layoutAnnotationCards);});
    const annotationIcons={
      comment:'<svg class="annotation-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M7 18 3 21V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H7Z"></path><path d="M8 8h8M8 12h5"></path></svg>',
      send:'<svg class="annotation-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M10 15V5m-4 4 4-4 4 4"></path></svg>',
      stop:'<svg class="annotation-icon" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true" focusable="false"><rect x="5" y="5" width="10" height="10" rx="1.5"></rect></svg>'
    };
    const annotationBusy=c=>['queued','starting','running','stopping'].includes(c?.status);
    const annotationCanSend=()=>!!endpoint&&!shared&&codexEnabled&&ann.agent.enabled&&ann.agent.available;
    function annotationStorage(kind,value){try{localStorage.setItem(storageKeys[kind],JSON.stringify(value));return true;}catch{ann.error='浏览器存储空间不足，请导出批注后重试';return false;}}
    function storeAnnotationDraft(){return annotationStorage('annotationDraft',ann.draft);}
    function currentAnnotation(){return ann.items.find(c=>c.id===ann.current);}
    function annotationReason(){return shared?'共享模式仅保存批注，Agent 不可用':!endpoint?'离线模式仅保存批注，不会启动 Agent':ann.agent.reason||'当前未启用 Agent，仅保存批注';}
    function annotationReadingBookmark(){
      const root=query(script.dataset.annotationRoot)||document.querySelector('main,article,[role=main]')||document.body;
      const box=root.getBoundingClientRect(),x=Math.max(8,Math.min(innerWidth-340,box.left+Math.min(90,box.width/3))),y=Math.min(110,innerHeight/4);
      const element=document.elementFromPoint(x,y)?.closest('p,h1,h2,h3,h4,h5,h6,li,blockquote,pre,section,article,main');
      if(!element||element.contains(host))return null;
      return {selector:path(element),top:element.getBoundingClientRect().top};
    }
    function saveAnnotationView(){
      if(!ann.viewReady||ann.viewPage!==pageKey(location.href))return false;
      const root=annotationScrollRoot(),field=ui.activeElement,view={version:1,open:ann.open,current:ann.current,filter:ann.filter,expanded:ann.expanded,
        scrollTop:root.scrollTop,scrollLeft:root.scrollLeft,windowX:scrollX,windowY:scrollY,drawerScrollTop:ui.querySelector('.annotation-sidebar')?.scrollTop||0,
        reading:annotationReadingBookmark(),focus:['annotation-input','annotation-followup'].includes(field?.id)?{id:field.id,start:field.selectionStart,end:field.selectionEnd}:null};
      try{sessionStorage.setItem(annotationViewKey(ann.viewPage),JSON.stringify(view));return true;}catch{return false;}
    }
    function syncAnnotationIdentity(){
      const page=pageKey(location.href);if(page===ann.viewPage)return;
      // The previous view is saved as it changes, before hash/history navigation.
      // Never write the old card selection into the new page's storage key.
      ann.viewPage=page;ann.viewEpoch++;ann.viewReady=false;ann.restoringView=null;
      savedAnnotationView=readAnnotationView(page);
      ann.open=!!savedAnnotationView?.open;ann.current=savedAnnotationView?.current||null;
      ann.filter=['open','all','resolved'].includes(savedAnnotationView?.filter)?savedAnnotationView.filter:'open';ann.expanded=savedAnnotationView?.expanded||{};
      ann.editVersions.clear();ann.observedEdits=false;ann.refreshPending=null;ann.selection=null;
    }
    async function restoreAnnotationView(){
      if(ann.viewReady)return;
      if(ann.restoringView)return ann.restoringView;
      const epoch=ann.viewEpoch;
      const restoring=(async()=>{
      if(!await stylesReady||epoch!==ann.viewEpoch)return;
      const saved=savedAnnotationView;savedAnnotationView=null;
      if(saved){
        await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        if(epoch!==ann.viewEpoch)return;
        syncAnnotationLayout();renderAnnotations();drawAnnotations();
        const root=annotationScrollRoot(),number=value=>Number.isFinite(value)?value:0;
        window.scrollTo(number(saved.windowX),number(saved.windowY));root.scrollLeft=number(saved.scrollLeft);root.scrollTop=number(saved.scrollTop);
        const reading=saved.reading&&query(saved.reading.selector);
        if(reading&&Number.isFinite(saved.reading.top))annotationScrollBy(reading.getBoundingClientRect().top-saved.reading.top);
        drawAnnotations();
        const sidebar=ui.querySelector('.annotation-sidebar');if(sidebar&&ann.layout==='drawer')sidebar.scrollTop=number(saved.drawerScrollTop);
        const field=saved.focus&&$(saved.focus.id),active=document.activeElement;
        if(field?.value&&(!active||[document.body,document.documentElement,host].includes(active))){field.focus({preventScroll:true});field.setSelectionRange(number(saved.focus.start),number(saved.focus.end));}
      }
      if(epoch===ann.viewEpoch){ann.viewReady=true;saveAnnotationView();}
      })();
      ann.restoringView=restoring;
      try{await restoring;}finally{if(ann.restoringView===restoring)ann.restoringView=null;}
    }
    function annotationFieldValue(field){
      if(field.isContentEditable)return field.innerHTML;
      if(field.matches('input[type=checkbox],input[type=radio]'))return field.checked;
      if(field.matches('select'))return [...field.options].map(option=>option.selected).join(',');
      return field.value;
    }
    function observeAnnotationEditing(e,eventPath){
      if(eventPath.includes(host))return;
      const field=eventPath.find(el=>el?.matches?.('input,textarea,select,[contenteditable]:not([contenteditable="false"])'));
      if(!field)return;
      if(['focusin','beforeinput'].includes(e.type)&&!ann.externalValues.has(field))ann.externalValues.set(field,annotationFieldValue(field));
      if(['input','change'].includes(e.type)){
        if(!ann.externalValues.has(field))ann.externalValues.set(field,field.defaultValue??null);
        if(annotationFieldValue(field)===ann.externalValues.get(field))ann.externalDirty.delete(field);else ann.externalDirty.add(field);
      }
    }
    function annotationReloadBlocked(){
      for(const field of ann.externalDirty)if(!field.isConnected)ann.externalDirty.delete(field);
      const focused=document.activeElement,externalFocus=focused&&focused!==host&&focused.matches('input,textarea,select,[contenteditable]:not([contenteditable="false"])');
      return !ann.viewReady||ann.sending||ann.adding||ann.composing||ann.draft||ann.selection||Object.values(ann.chats).some(text=>String(text).trim())||
        Object.keys(ann.requests).some(key=>!key.endsWith(':initial'))||ann.externalDirty.size||externalFocus||unsavedReview()||state.selected||state.saving||state.adding||
        state.codexSending||state.chatSending||Object.values(state.chatDrafts).some(text=>String(text).trim())||codexBusy()||ann.items.some(record=>annotationBusy(record.conversation));
    }
    function observeAnnotationBuild(build){
      if(!ann.loadedBuild)ann.loadedBuild=build;
      if(!endpoint||shared||!codexEnabled||!ann.agent.enabled)return;
      for(const record of annotationPageRecords()){
        if(annotationBusy(record.conversation))continue;
        const version=String(record.updatedAt||'');
        if(ann.observedEdits&&record.status==='changed'&&record.conversation?.status==='completed'&&ann.editVersions.get(record.id)!==version&&build&&build!==ann.loadedBuild)ann.refreshPending=build;
        ann.editVersions.set(record.id,version);
      }
      ann.observedEdits=true;
      if(ann.refreshPending){if(build===ann.loadedBuild)ann.refreshPending=null;else if(build)ann.refreshPending=build;}
    }
    function maybeReloadAnnotationPage(explicit=false){
      if(!ann.refreshPending||ann.reloading)return;
      if(annotationReloadBlocked()){if(explicit)notice('内容已更新，请先保存或清空当前输入，随后会自动刷新');return;}
      if(!saveAnnotationView()){if(explicit)notice('无法保存批注位置，请允许浏览器存储后重试刷新');return;}
      ann.reloading=true;location.reload();
    }
    function annotationContainer(range){let el=range.commonAncestorContainer.nodeType===1?range.commonAncestorContainer:range.commonAncestorContainer.parentElement;while(el&&getComputedStyle(el).display==='inline')el=el.parentElement;return el;}
    function annotationExcluded(node){const el=node?.nodeType===1?node:node?.parentElement;return !el||el.closest('input,textarea,select,button,[contenteditable]:not([contenteditable="false"]),script,style,noscript,[data-review-ignore]')||node.getRootNode()!==document;}
    function scheduleAnnotationSelection(){clearTimeout(ann.selectionTimer);ann.selectionTimer=setTimeout(readAnnotationSelection,60);}
    function readAnnotationSelection(){
      if(state.active){ann.selection=null;drawAnnotations();return;}
      const selection=getSelection();
      if(!selection?.rangeCount||selection.isCollapsed){ann.selection=null;drawAnnotations();return;}
      const range=selection.getRangeAt(0);
      if(annotationExcluded(range.startContainer)||annotationExcluded(range.endContainer)||!range.toString().trim()){ann.selection=null;drawAnnotations();return;}
      const el=annotationContainer(range);if(!el||el===host||el.contains(host)||el.querySelector('input,textarea,[contenteditable="true"]')&&range.cloneContents().querySelector?.('input,textarea,[contenteditable="true"]')){ann.selection=null;drawAnnotations();return;}
      const before=document.createRange();before.selectNodeContents(el);before.setEnd(range.startContainer,range.startOffset);
      const start=before.toString().length,exact=range.toString(),text=el.textContent||'';
      if(exact!==text.slice(start,start+exact.length)){ann.selection=null;drawAnnotations();return;}
      const bounds=rect(range.getBoundingClientRect());if(!bounds.width||!bounds.height)return;
      const a=anchor(el,bounds,'text',exact);a.textRange={start,end:start+exact.length,exact,prefix:text.slice(Math.max(0,start-40),start),suffix:text.slice(start+exact.length,start+exact.length+40)};
      ann.selection={anchor:a,page:pageContext(),range:range.cloneRange()};drawAnnotations();
    }
    function restoreAnnotationRange(a){
      const el=query(a?.selector),t=a?.textRange;if(!el||!t||typeof t.exact!=='string'||!t.exact)return null;
      const text=el.textContent||'',contextFits=i=>(!t.prefix||text.slice(Math.max(0,i-t.prefix.length),i)===t.prefix)&&(!t.suffix||text.slice(i+t.exact.length,i+t.exact.length+t.suffix.length)===t.suffix);
      let start=t.start;
      if(text.slice(start,t.end)!==t.exact||!contextFits(start)){
        const hits=[];let offset=0,index;while((index=text.indexOf(t.exact,offset))!==-1){if(contextFits(index))hits.push(index);offset=index+Math.max(1,t.exact.length);}
        if(hits.length!==1)return null;start=hits[0];
      }
      const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT),end=start+t.exact.length;let offset=0,first=null,last=null,node;
      while((node=walker.nextNode())){const length=node.textContent.length;if(first===null&&offset+length>start)first=[node,start-offset];if(offset+length>=end){last=[node,end-offset];break;}offset+=length;}
      if(!first||!last)return null;const range=document.createRange();try{range.setStart(...first);range.setEnd(...last);return range.toString()===t.exact?range:null;}catch{return null;}
    }
    const annotationOriginalElements=new WeakMap();
    function annotationLocation(a){
      const range=restoreAnnotationRange(a),element=query(a?.selector);
      const result=(kind,el=null,exact=null)=>({kind,element:el,range:exact,getBoundingClientRect:()=>exact?exact.getBoundingClientRect():el?.getBoundingClientRect()||null});
      if(range)return result('exact',element,range);
      if(!a||!element||!unique(a.selector)||annotationExcluded(element)||['HTML','BODY'].includes(element.tagName)||element.contains(host))return result('missing');
      let original=annotationOriginalElements.get(a);
      if(original===undefined){const template=document.createElement('template');template.innerHTML=a.html||'';original=template.content.firstElementChild||null;annotationOriginalElements.set(a,original);}
      if(!original||original.tagName!==element.tagName||a.tag&&a.tag!==element.tagName)return result('missing');
      // Stable identity names the logical block even when all of its text changes.
      // A positional selector alone cannot identify a replacement at the old index.
      const stableId=original.id&&original.id===element.id&&unique('#'+CSS.escape(original.id));
      const stableAttribute=[...original.attributes].some(attr=>/^data-(review-id|testid|node|edge|id|key)$/.test(attr.name)&&attr.value&&element.getAttribute(attr.name)===attr.value&&unique(element.tagName.toLowerCase()+'['+attr.name+'="'+CSS.escape(attr.value)+'"]'));
      if(stableId||stableAttribute)return result('block',element);
      if(original.id||/:(?:nth|first|last|only)-(?:child|of-type)|[+~]/.test(a.selector))return result('missing');
      const text=element.textContent||'',t=a.textRange||{},contexts=[t.prefix||'',t.suffix||''].map(value=>value.trim()?value:'');
      const distinctive=contexts.filter(value=>value.trim().length>=12);
      const positions=contexts.map(value=>value?text.indexOf(value):-1);
      if(!distinctive.length||contexts.some((value,i)=>value&&(positions[i]<0||text.lastIndexOf(value)!==positions[i]))||contexts.every(Boolean)&&positions[0]>=positions[1])return result('missing');
      return result('block',element);
    }
    function annotationDocumentTop(record,location=annotationLocation(record.anchor)){
      const bounds=location.getBoundingClientRect();
      return bounds?bounds.top+annotationScrollRoot().scrollTop:Math.max(60,Number(record.anchor?.documentRect?.y??record.anchor?.rect?.y)||60);
    }
    function annotationPageRecords(){return ann.items.filter(c=>pageKey(c.page.path)===pageKey(location.href));}
    function annotationVisibleRecords(){return annotationPageRecords().filter(c=>ann.filter==='all'||(ann.filter==='resolved'?c.status==='resolved':c.status!=='resolved'));}
    function annotationOrder(records){return records.slice().sort((a,b)=>{const la=annotationLocation(a.anchor),lb=annotationLocation(b.anchor);if(la.range&&lb.range)return la.range.compareBoundaryPoints(Range.START_TO_START,lb.range)||(a.number||0)-(b.number||0);if(la.element&&lb.element){if(la.element===lb.element)return (a.anchor.textRange?.start||0)-(b.anchor.textRange?.start||0)||(a.number||0)-(b.number||0);const order=la.element.compareDocumentPosition(lb.element);if(order&Node.DOCUMENT_POSITION_FOLLOWING)return -1;if(order&Node.DOCUMENT_POSITION_PRECEDING)return 1;}return annotationDocumentTop(a,la)-annotationDocumentTop(b,lb)||(a.number||0)-(b.number||0);});}
    function annotationScrollRoot(){return query(script.dataset.annotationScrollRoot)||document.scrollingElement;}
    function annotationScrollBy(delta){const root=annotationScrollRoot();if(root===document.scrollingElement)window.scrollBy(0,delta);else root.scrollTop+=delta;}
    function readingPosition(){const x=Math.min(120,innerWidth/4),y=Math.min(100,innerHeight/4),el=document.elementFromPoint(x,y);if(!el||el.contains(host))return null;const caret=document.caretRangeFromPoint?.(x,y);if(caret&&caret.startContainer.nodeType===Node.TEXT_NODE){const range=caret.cloneRange();if(range.startOffset<range.startContainer.length)range.setEnd(range.startContainer,range.startOffset+1);return {range,top:range.getBoundingClientRect().top};}return {el,top:el.getBoundingClientRect().top};}
    function restoreReading(pos){if(pos?.range?.startContainer.isConnected)annotationScrollBy(pos.range.getBoundingClientRect().top-pos.top);else if(pos?.el?.isConnected)annotationScrollBy(pos.el.getBoundingClientRect().top-pos.top);}
    function syncAnnotationLayout(){
      if(!stylesLoaded)return;
      if(!ann.open){if(ann.reserve){const pos=readingPosition();if(ann.reserve.styleAttribute===null)ann.reserve.el.removeAttribute('style');else ann.reserve.el.setAttribute('style',ann.reserve.styleAttribute);ann.reserve=null;ann.tail?.remove();ann.tail=null;restoreReading(pos);}return;}
      const explicit=query(script.dataset.annotationRoot),scroll=annotationScrollRoot(),body=document.body;
      const fixed=[...body.children].some(el=>el!==host&&el!==ann.tail&&getComputedStyle(el).position==='fixed'&&el.getBoundingClientRect().width>innerWidth*.7);
      const nested=[...body.querySelectorAll('main,article,[role=main]')].some(el=>/auto|scroll/.test(getComputedStyle(el).overflowY)&&el.scrollHeight>el.clientHeight+20&&el.clientHeight<innerHeight+10);
      const safe=innerWidth>760&&(explicit||(!fixed&&!nested&&!['grid','inline-grid'].includes(getComputedStyle(body).display)&&scroll===document.scrollingElement&&getComputedStyle(body).overflowX!=='hidden'));
      const target=safe?(explicit||body):null;
      if(ann.reserve?.el!==target){const pos=readingPosition();if(ann.reserve){if(ann.reserve.styleAttribute===null)ann.reserve.el.removeAttribute('style');else ann.reserve.el.setAttribute('style',ann.reserve.styleAttribute);ann.reserve=null;ann.tail?.remove();ann.tail=null;}if(target){const names=['padding-right','box-sizing'];ann.reserve={el:target,styleAttribute:target.getAttribute('style'),styles:names.map(name=>[name,target.style.getPropertyValue(name),target.style.getPropertyPriority(name)])};const padding=parseFloat(getComputedStyle(target).paddingRight)||0;target.style.setProperty('padding-right',(padding+320)+'px');target.style.setProperty('box-sizing','border-box');ann.tail=document.createElement('div');ann.tail.dataset.reviewIgnore='true';ann.tail.setAttribute('aria-hidden','true');ann.tail.style.cssText='height:0;flex-shrink:0;pointer-events:none;clear:both';(scroll===document.scrollingElement?body:scroll).append(ann.tail);}restoreReading(pos);}
      ann.layout=target?'aligned':'drawer';
      const color=getComputedStyle(body).backgroundColor.match(/[\d.]+/g),rgb=color&&color.length>=3?color.slice(0,3).map(Number):[255,255,255];
      ann.dark=color&&Number(color[3]??1)>0&&rgb.reduce((a,b)=>a+b,0)<390;
      $('annotation-panel').dataset.theme=ann.dark?'dark':'light';
    }
    function drawAnnotations(){
      const floating=$('annotation-selection');
      if(ann.selection&&!state.active){const r=ann.selection.range.getBoundingClientRect();if(!floating.firstChild)floating.innerHTML='<button class="annotation-create-button" data-action="annotation-create" aria-label="为选中文字添加内容批注" title="添加批注">'+annotationIcons.comment+'</button>';const color=getComputedStyle(document.body).backgroundColor.match(/[\d.]+/g);floating.dataset.theme=color&&Number(color[3]??1)>0&&color.slice(0,3).map(Number).reduce((a,b)=>a+b,0)<390?'dark':'light';const box=floating.firstChild.getBoundingClientRect();floating.style.left=Math.max(8,Math.min(innerWidth-box.width-8,r.right-box.width))+'px';floating.style.top=Math.max(8,r.bottom+box.height+16<innerHeight?r.bottom+8:r.top-box.height-8)+'px';}else floating.innerHTML='';
      const records=state.active?[]:annotationVisibleRecords();
      if(!state.active&&ann.open&&ann.draft&&pageKey(ann.draft.page.path)===pageKey(location.href)&&!records.some(c=>c.id===ann.draft.id))records.push({...ann.draft,number:'…'});
      const markup=records.map(c=>{const location=annotationLocation(c.anchor),range=location.range,r=location.getBoundingClientRect();if(!r)return '';const highlight=range?[...range.getClientRects()].filter(r=>r.width&&r.height&&r.bottom>0&&r.top<innerHeight).map(r=>`<span class="annotation-highlight ${c.id===ann.current?'selected':''}" data-id="${esc(c.id)}" style="left:${r.x}px;top:${r.y}px;width:${r.width}px;height:${r.height}px"></span>`).join(''):'';const block=location.kind==='block';return highlight+(c.number!=='…'&&r.width&&r.height&&r.bottom>0&&r.top<innerHeight?`<button class="annotation-marker${block?' annotation-marker-block':''}" data-action="annotation-open" data-id="${esc(c.id)}" aria-label="查看内容批注 ${c.number}${block?'，原文已变化，定位到原段落':''}" ${block?'title="原文已变化 · 保留在原段落旁"':''} style="left:${Math.max(2,Math.min(innerWidth-24,r.right+3))}px;top:${Math.max(2,r.top-8)}px">${c.number}</button>`:'');}).join('');
      if($('annotation-highlights').innerHTML!==markup)$('annotation-highlights').innerHTML=markup;
      layoutAnnotationCards();
    }
    function locateAnnotation(record){const location=annotationLocation(record?.anchor),r=location.getBoundingClientRect();if(location.kind!=='exact')notice('原文位置已变化，请查看保留的引用和截图');if(!r){const card=[...($('annotation-cards')?.children||[])].find(el=>el.dataset.id===record?.id);if(card&&ann.layout==='aligned'){const top=card.getBoundingClientRect().top;if(top<64||top>innerHeight-100)annotationScrollBy(top-90);}drawAnnotations();return;}if(r.top<64||r.bottom>innerHeight-80)annotationScrollBy(r.top-Math.max(80,innerHeight*.28));drawAnnotations();}
    function openAnnotations(id=null){ann.open=true;ann.current=id||(!ann.current&&ann.draft?ann.draft.id:ann.current);if(id)ann.lastAnchor=id;ann.error='';state.list=false;state.codexPanel=false;renderList();renderCodex();syncAnnotationLayout();renderAnnotations();toolbar();drawAnnotations();if(id&&ann.layout==='drawer')requestAnimationFrame(()=>ui.querySelector('.annotation-card[data-active=true]')?.scrollIntoView({block:'nearest'}));}
    function annotationImages(images,editable=false,id=''){return images?.length?`<div class="attachments">${images.map((image,i)=>`<div class="attachment"><button class="attachment-preview" data-action="annotation-preview" data-id="${esc(id)}" data-index="${i}" aria-label="预览批注附图 ${i+1}"><img src="${esc(imageSource(image))}" alt="批注附图 ${i+1}"></button>${editable?`<button class="attachment-remove" data-action="annotation-remove-image" data-index="${i}" aria-label="移除批注附图 ${i+1}">×</button>`:''}</div>`).join('')}</div>`:'';}
    function setAnnotationMarkup(id,markup){const el=$(id);if(el&&el.innerHTML!==markup)el.innerHTML=markup;}
    function annotationDate(value){const numeric=typeof value==='number'||/^\d+(?:\.\d+)?$/.test(String(value))?Number(value):NaN,date=Number.isFinite(numeric)?new Date(numeric>=1e17?numeric/1e6:numeric>=1e14?numeric/1e3:numeric>=1e11?numeric:numeric*1000):new Date(value);return Number.isNaN(date.getTime())?'':date.toLocaleDateString();}
    function annotationMessages(record){
      const c=record.conversation||{},visible=[];
      for(const [i,message] of (c.messages||[]).entries()){
        if(!message.text||message.role==='user'&&(c.initialMessageId?message.id===c.initialMessageId:c.hasAgent!==false&&c.status!=='saved'&&i===0&&message.text===record.text))continue;
        if(message.role==='assistant'){
          // A turn may stream commentary and a final item. Display its latest item once;
          // preserve the complete raw conversation in the saved/exported JSON evidence.
          const sameTurn=message.turnId?visible.findIndex(m=>m.role==='assistant'&&m.turnId===message.turnId):-1;
          if(sameTurn>=0){visible[sameTurn]=message;continue;}
          const previous=visible[visible.length-1];
          if(!message.turnId&&previous?.role==='assistant'&&!previous.turnId){visible[visible.length-1]=message;continue;}
        }
        visible.push(message);
      }
      if(c.result&&!visible.some(m=>m.role==='assistant'&&m.text===c.result)){
        const latest=visible.map(m=>m.role).lastIndexOf('assistant');
        if(latest<0)visible.push({id:'result',role:'assistant',text:c.result});
        else if(c.status==='completed')visible[latest]={...visible[latest],text:c.result};
      }
      return visible;
    }
    function annotationReplyPreference(id){return ann.requests[id+':annotation-message']?.autoReply??(ann.draft?.id===id?(ann.draft.pending?.autoReply??ann.draft.autoReply!==false):ann.replyAgent[id]!==false);}
    function annotationComposer(record,draft){const id=record.id,pending=draft?!!record.pending:!!ann.requests[id+':annotation-message'];return `<div class="annotation-compose"><label class="sr-only" for="${draft?'annotation-input':'annotation-followup'}">${draft?'内容批注':'继续讨论这条批注'}</label><textarea id="${draft?'annotation-input':'annotation-followup'}" rows="2" maxlength="${draft?10000:4000}" placeholder="${draft?'询问这段内容，或说明希望如何修改…':'回复，或补充修改要求…'}" ${pending?'disabled':''}></textarea>${draft?'<div id="annotation-images"></div>':''}<div class="annotation-compose-actions">${draft?'<button data-action="annotation-add-image" title="添加图片" aria-label="添加图片">＋ 图片</button><input id="annotation-image-input" type="file" accept="image/png,image/jpeg,image/webp,image/gif" multiple hidden>':'<span></span>'}<button class="primary annotation-send-button" data-action="${draft?'annotation-send':'annotation-message'}" data-id="${esc(id)}" title="⌘ / Ctrl + Enter">发送 ↑</button></div><div class="annotation-agent-line"><button id="annotation-agent-toggle" role="switch" data-action="annotation-agent-toggle" data-id="${esc(id)}" aria-checked="false">Agent响应 <span aria-hidden="true"></span></button><small id="annotation-capability"></small></div></div>`;}
    function reconcileAnnotationCardOrder(root,records){
      const byId=new Map([...root.children].map(card=>[card.dataset.id,card]));
      const ordered=annotationOrder(records).map(record=>byId.get(record.id)).filter(Boolean);
      // Never detach the active composer: moving its siblings around it preserves
      // native focus, selection and IME even on browsers without moveBefore().
      const protectedCard=ordered.find(card=>card.contains(ui.activeElement))||byId.get(ann.current);
      const pivot=ordered.indexOf(protectedCard),place=(nodes,before)=>{
        for(let i=nodes.length-1;i>=0;i--){const card=nodes[i];if(card.nextSibling!==before)root.insertBefore(card,before);before=card;}
      };
      if(pivot>=0){place(ordered.slice(0,pivot),protectedCard);place(ordered.slice(pivot+1),null);}
      else place(ordered,null);
    }
    function renderAnnotationMeta(card,record,isDraft){
      const meta=card.querySelector('[data-part="meta"]'),kind=isDraft?'draft':'record';
      // Native details.open and focus belong to the reader, not the polling renderer.
      if(meta.dataset.kind!==kind){
        meta.dataset.kind=kind;
        meta.innerHTML='<small data-meta="author"></small><small data-meta="changed" class="annotation-changed" hidden>待验收</small>'+(isDraft?'<button class="annotation-draft-close" data-action="annotation-discard" aria-label="放弃草稿" title="放弃草稿">×</button>':'<details class="annotation-menu"><summary aria-label="批注选项">···</summary><div><button data-action="annotation-status"></button><button data-action="annotation-snapshot">查看截图</button></div></details>');
      }
      const author=meta.querySelector('[data-meta="author"]'),date=annotationDate(record.createdAt),label=isDraft?'':date;
      if(author.textContent!==label)author.textContent=label;
      author.hidden=!label;
      meta.querySelector('[data-meta="changed"]').hidden=record.status!=='changed';
      if(!isDraft){
        const status=meta.querySelector('[data-action="annotation-status"]'),snapshot=meta.querySelector('[data-action="annotation-snapshot"]');
        status.dataset.id=snapshot.dataset.id=record.id;status.dataset.status=record.status==='resolved'?'open':'resolved';
        const text=record.status==='resolved'?'重新打开':'标为解决';if(status.textContent!==text)status.textContent=text;
        snapshot.disabled=!(record.screenshot||record.screenshotData);
      }
    }
    function closeAnnotationMenus(except=null,restoreFocus=false){
      const menus=[...ui.querySelectorAll('.annotation-menu[open]')].filter(menu=>menu!==except);
      for(const menu of menus)menu.open=false;
      if(restoreFocus)menus[menus.length-1]?.querySelector('summary')?.focus();
      return menus.length>0;
    }
    function renderAnnotations(){
      if(!stylesLoaded)return;
      const panel=$('annotation-panel');if(!ann.open){syncAnnotationLayout();panel.innerHTML='';saveAnnotationView();return;}syncAnnotationLayout();
      if(!panel.firstElementChild){panel.innerHTML='<section class="annotation-sidebar" aria-label="页面内容批注"><header><strong id="annotation-title"></strong><nav aria-label="批注导航"><button data-action="annotation-prev" aria-label="上一条批注">↑</button><button data-action="annotation-next" aria-label="下一条批注">↓</button><details class="annotation-menu"><summary aria-label="更多批注选项">···</summary><div><button data-action="annotation-filter" data-filter="open">未解决</button><button data-action="annotation-filter" data-filter="all">全部</button><button data-action="annotation-filter" data-filter="resolved">已解决</button><button data-action="annotation-export">导出批注</button><button data-action="annotation-refresh">重新同步</button></div></details><button data-action="annotation-reload" aria-label="刷新页面内容" title="内容已更新；保留当前输入，保存后自动刷新" hidden>更新</button><button data-action="annotation-close" aria-label="收起内容批注">×</button></nav></header><div class="annotation-drawer-back"><button data-action="annotation-return">← 返回原文</button><span id="annotation-drawer-quote"></span></div><div id="annotation-empty"></div><div id="annotation-cards"></div><div id="annotation-error" class="error" role="alert"></div></section>';}
      panel.firstElementChild.dataset.layout=ann.layout;
      ui.querySelector('[data-action=annotation-reload]').hidden=!ann.refreshPending;
      const records=annotationOrder(annotationVisibleRecords()),draft=ann.draft&&pageKey(ann.draft.page.path)===pageKey(location.href)&&!records.some(c=>c.id===ann.draft.id)?ann.draft:null;
      if(draft)records.push(draft);
      const total=annotationPageRecords().length;$('annotation-title').textContent='批注 · '+annotationVisibleRecords().length+' · '+({all:'全部',resolved:'已解决',open:'未解决'}[ann.filter])+(ann.filter==='all'?'':' / '+total);
      $('annotation-error').textContent=ann.error;
      const cards=$('annotation-cards'),ids=new Set(records.map(c=>c.id));for(const card of [...cards.children])if(!ids.has(card.dataset.id)){annotationCardResize.unobserve(card);card.remove();}
      // IDs identify only the active card. Keyed card nodes survive polling and input composition.
      for(const card of cards.children)for(const el of card.querySelectorAll('[id]'))if(!['annotation-input','annotation-followup','annotation-agent-toggle','annotation-capability','annotation-images','annotation-image-input'].includes(el.id))el.removeAttribute('id');
      for(const record of records){let card=[...cards.children].find(el=>el.dataset.id===record.id);if(!card){card=document.createElement('article');card.className='annotation-card';card.dataset.id=record.id;card.tabIndex=0;card.innerHTML='<button class="annotation-quote" data-part="quote" data-action="annotation-open"></button><div class="annotation-card-meta" data-part="meta"></div><div data-part="original"></div><div data-part="thread" class="annotation-thread" role="log" aria-label="批注对话"></div><div class="annotation-activity"><div data-part="state" class="annotation-state" role="status" aria-live="polite"></div><div data-part="controls" class="annotation-controls"></div></div><div data-part="composer"></div>';cards.append(card);annotationCardResize.observe(card);}const part=name=>card.querySelector('[data-part="'+name+'"]'),set=(name,markup)=>{if(part(name).innerHTML!==markup)part(name).innerHTML=markup;},active=ann.current===record.id,isDraft=record===draft;
        card.classList.toggle('active',active);card.dataset.draft=String(isDraft);card.setAttribute('aria-label',isDraft?'新批注':'批注 '+record.number);
        const quote=part('quote');quote.dataset.id=record.id;quote.textContent=record.anchor.selectedText||record.anchor.textRange?.exact||'';quote.title=quote.textContent;
        renderAnnotationMeta(card,record,isDraft);
        set('original',isDraft?'':`<p class="annotation-text"><span class="annotation-speaker">我：</span><span class="annotation-message-content">${esc(record.text)}</span></p>${annotationImages(record.attachments,false,record.id)}`);
        set('thread',isDraft?'':annotationMessages(record).map((m,i)=>{const key=m.id||String(i),long=m.text.length>500,expanded=ann.expanded[record.id+':'+key];return `<div class="annotation-message ${m.role==='user'?'from-user':'from-agent'}" role="group" aria-label="${m.role==='user'?'我的回复':'Agent 回复'}"><p class="${long&&!expanded?'annotation-collapsed':''}"><span class="annotation-speaker">${m.role==='user'?'我：':'Agent：'}</span><span class="annotation-message-content">${esc(m.text)}</span></p>${long?`<button data-action="annotation-expand" data-id="${esc(record.id)}" data-message="${esc(key)}">${expanded?'收起回复':'展开回复'}</button>`:''}</div>`;}).join(''));
        const c=record.conversation||{},busy=annotationBusy(c),unlocated=annotationLocation(record.anchor).kind!=='exact',progress=busy?esc({queued:'等待 Agent',starting:'Agent 回复中…',running:'Agent 回复中…',stopping:'正在停止'}[c.status]):c.status==='failed'?esc(c.error||'Agent 回复失败'):c.status==='cancelled'?'已停止':'';card.dataset.busy=String(busy);set('state',(progress?'<span>'+progress+'</span>':'')+(unlocated?'<span>原文已变化 · 引用与截图仍保留</span>':''));
        set('controls',isDraft?'':`${ann.draft?.id===record.id&&ann.draft.pending?'<button data-action="annotation-confirm">重试确认发送</button>':!c.hasAgent&&!annotationBusy(c)&&annotationCanSend()?`<button data-action="annotation-start" data-id="${esc(record.id)}">让 Agent 处理</button>`:''}${busy?`<button class="annotation-stop-button" data-action="annotation-stop" data-id="${esc(record.id)}" aria-label="${c.status==='stopping'?'正在停止回复':c.status==='queued'?'取消排队':'停止回复'}" title="${c.status==='stopping'?'正在停止回复':c.status==='queued'?'取消排队':'停止回复'}"${c.status==='stopping'||!annotationCanSend()?' disabled=""':''}>${annotationIcons.stop}</button>`:['failed','cancelled'].includes(c.status)?`<button data-action="annotation-retry" data-id="${esc(record.id)}" ${annotationCanSend()?'':'disabled'}>重试</button>`:''}`);
        const compose=part('composer');if(active&&(!compose.firstChild||compose.dataset.kind!==(isDraft?'draft':'reply'))){compose.dataset.kind=isDraft?'draft':'reply';for(const other of cards.querySelectorAll('[data-part=composer]'))if(other!==compose)other.replaceChildren();compose.innerHTML=annotationComposer(record,isDraft);const input=$(isDraft?'annotation-input':'annotation-followup');input.value=isDraft?record.text||'':ann.chats[record.id]||'';}else if(!active&&compose.firstChild)compose.replaceChildren();
        if(active){quote.id='annotation-quote';part('original').id='annotation-original';part('thread').id='annotation-thread';part('state').id='annotation-state';part('controls').id='annotation-controls';card.dataset.active='true';}else delete card.dataset.active;
      }
      reconcileAnnotationCardOrder(cards,records);
      const active=currentAnnotation()||(draft?.id===ann.current?draft:null);$('annotation-drawer-quote').textContent=active?.anchor?.selectedText||'';if(active){const isDraft=active===draft,pending=isDraft?!!draft.pending:!!ann.requests[active.id+':annotation-message'],toggle=$('annotation-agent-toggle');if(toggle){toggle.setAttribute('aria-checked',String(annotationCanSend()&&annotationReplyPreference(active.id)));toggle.disabled=!annotationCanSend()||pending||ann.sending;toggle.title=pending?'待确认消息沿用原发送选择':annotationCanSend()?'本次发送交给 Agent 响应':annotationReason();$('annotation-capability').textContent=pending?'发送待确认':annotationCanSend()?'':annotationReason();}const field=$(isDraft?'annotation-input':'annotation-followup');if(field)field.disabled=ann.sending||pending;setAnnotationMarkup('annotation-images',isDraft?annotationImages(draft.attachments,true):'');}
      const ordered=annotationOrder(annotationVisibleRecords()),index=ordered.findIndex(c=>c.id===ann.current);ui.querySelector('[data-action=annotation-prev]').disabled=!ordered.length||index===0;ui.querySelector('[data-action=annotation-next]').disabled=!ordered.length||index===ordered.length-1;
      updateAnnotationSend();layoutAnnotationCards();requestAnimationFrame(layoutAnnotationCards);saveAnnotationView();
    }
    function layoutAnnotationCards(){
      if(!ann.open||!$('annotation-cards'))return;const root=$('annotation-cards'),records=annotationOrder(annotationVisibleRecords());if(ann.draft&&pageKey(ann.draft.page.path)===pageKey(location.href)&&!records.some(c=>c.id===ann.draft.id))records.push(ann.draft);
      const entries=records.map(record=>{const card=[...root.children].find(el=>el.dataset.id===record.id),location=annotationLocation(record.anchor),bounds=location.getBoundingClientRect();return {record,card,location,bounds};}).filter(e=>e.card);
      if(ann.layout==='drawer'){entries.forEach(e=>{e.card.style.removeProperty('top');});root.style.removeProperty('height');$('annotation-empty').innerHTML=entries.length?'':'<p>阅读时选中文字，即可添加批注。</p>';return;}
      const scroll=annotationScrollRoot().scrollTop;for(const e of entries){e.target=annotationDocumentTop(e.record,e.location);e.top=e.target;}
      const active=entries.findIndex(e=>e.record.id===ann.current);if(active>=0){for(let i=active-1;i>=0;i--)entries[i].top=Math.min(entries[i].target,entries[i+1].top-entries[i].card.offsetHeight-16);for(let i=active+1;i<entries.length;i++)entries[i].top=Math.max(entries[i].target,entries[i-1].top+entries[i-1].card.offsetHeight+16);}else for(let i=1;i<entries.length;i++)entries[i].top=Math.max(entries[i].target,entries[i-1].top+entries[i-1].card.offsetHeight+16);
      for(const e of entries)e.card.style.top=(e.top-scroll)+'px';
      const visible=entries.some(e=>e.bounds?e.bounds.top<innerHeight-60&&e.bounds.bottom>60:e.top-scroll<innerHeight-60&&e.top-scroll+e.card.offsetHeight>60);const empty=entries.length&&!visible?'<button data-action="annotation-nearest">跳到最近批注</button>':!entries.length?'<p>阅读时选中文字，即可添加批注。</p>':'';if($('annotation-empty').innerHTML!==empty)$('annotation-empty').innerHTML=empty;
      if(ann.tail){const extent=Math.max(0,...entries.map(e=>e.top+e.card.offsetHeight+90)),base=ann.tail.getBoundingClientRect().top+scroll;const extra=Math.max(0,Math.ceil(extent-base));if(Math.abs(ann.tail.offsetHeight-extra)>2)ann.tail.style.height=extra+'px';}
    }
    function annotationSendLabel(button,label){const markup='<span>'+esc(label)+'</span>'+annotationIcons.send;if(button.innerHTML!==markup)button.innerHTML=markup;button.setAttribute('aria-label',label==='发送'?'发送批注':label);button.title=label==='发送'?'发送 · ⌘ / Ctrl + Enter':label;}
    function updateAnnotationSend(){const draft=ann.draft,button=ui.querySelector('[data-action="annotation-send"]');if(button){button.disabled=ann.sending||ann.adding||!draft||(!draft.text?.trim()&&!draft.attachments?.length);annotationSendLabel(button,ann.sending?'正在发送…':ann.adding?'正在读取图片…':draft?.pending?'重试确认发送':'发送');}const reply=ui.querySelector('[data-action="annotation-message"]');if(reply){const pending=ann.requests[ann.current+':annotation-message'];reply.disabled=ann.sending||(!pending&&!$('annotation-followup')?.value.trim());annotationSendLabel(reply,pending?'重试确认发送':ann.sending?'正在发送…':'发送');}ui.querySelectorAll('[data-action="annotation-add-image"],[data-action="annotation-remove-image"],[data-action="annotation-discard"]').forEach(el=>el.disabled=ann.sending||ann.adding||!!draft?.pending);}
    async function refreshAnnotations(){
      syncAnnotationIdentity();
      try{if(endpoint){const response=await fetch(endpoint+'annotations');if(!response.ok)throw Error('内容批注服务暂不可用');const data=await response.json();ann.items=data.annotations||[];ann.agent=data.agent||{enabled:false,available:false};observeAnnotationBuild(data.build);}else ann.items=readStorage(localStorage,'annotations','[]');toolbar();renderAnnotations();drawAnnotations();await restoreAnnotationView();maybeReloadAnnotationPage();}catch(error){ann.agent={enabled:false,available:false,reason:error.message};if(ann.open){ann.error=error.message;renderAnnotations();}}
    }
    async function annotationPost(route,payload){const response=await fetch(endpoint+'annotations'+route,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await response.json();if(!response.ok)throw Error(data.error||'批注操作失败，请重试');return data;}
    function mergeAnnotation(record){const index=ann.items.findIndex(c=>c.id===record.id);if(index<0)ann.items.push(record);else ann.items[index]=record;}
    async function sendAnnotation(){
      const draft=ann.draft;if(!draft||ann.sending||ann.adding||(!draft.text?.trim()&&!draft.attachments.length))return;ann.sending=true;ann.error='';renderAnnotations();
      try{
        if(!draft.pending){
          const data=fileMode?null:(draft.screenshotData||await ann.shot||await capture());if(!fileMode&&!data)throw Error('截图未生成，请重试发送');
          const record={id:draft.id,text:draft.text.trim(),status:'open',anchor:draft.anchor,page:draft.page,attachments:draft.attachments.map(image=>({...image})),...(data?{screenshotData:draft.screenshotData||await markSnapshot(data,draft.anchor.rect)}:{snapshotNote:'离线文件批注，未附截图'})};
          draft.pending={annotation:record,requestId:draft.requestId,autoReply:annotationCanSend()&&draft.autoReply!==false};if(!storeAnnotationDraft())throw Error(ann.error);
        }
        let record,dispatchError='';
        if(endpoint){const data=await annotationPost('',draft.pending);record=data.annotation;if(data.agentError){dispatchError=String(data.agentError);ann.error='批注已保存，Agent 派发待确认；'+dispatchError;}}
        else{record={...draft.pending.annotation,number:Math.max(0,...ann.items.map(c=>c.number||0))+1,createdAt:Date.now(),updatedAt:Date.now()};const records=ann.items.filter(c=>c.id!==record.id).concat(record);if(!annotationStorage('annotations',records))throw Error(ann.error);}
        ann.requests[record.id+':initial']={requestId:draft.requestId};annotationStorage('annotationRequests',ann.requests);mergeAnnotation(record);if(!dispatchError){ann.draft=null;ann.shot=null;storeAnnotationDraft();}ann.current=record.id;getSelection()?.removeAllRanges();notice('内容批注已保存');
      }catch(error){ann.error=error.message||'未收到发送确认，批注与请求已保留，请重试';}
      finally{ann.sending=false;renderAnnotations();toolbar();drawAnnotations();}
    }
    async function addAnnotationImages(files){
      const draft=ann.draft;if(!draft||draft.pending||ann.adding||ann.sending)return;
      try{if(draft.attachments.length+files.length>maxImages)throw Error('每条批注最多添加 6 张图片');if(files.some(f=>!imageTypes.includes(f.type)))throw Error('支持 PNG、JPEG、WebP 和 GIF 图片');if(files.some(f=>f.size>maxImageBytes))throw Error('每张图片不能超过 5 MB');if(files.reduce((n,f)=>n+f.size,0)+draft.attachments.reduce((n,f)=>n+f.size,0)>maxTotalImageBytes)throw Error('图片合计不能超过 10 MB');ann.adding=true;updateAnnotationSend();const images=await Promise.all(files.map(async file=>{const dataUrl=await fileData(file),image=new Image();image.src=dataUrl;await image.decode();return {id:requestId(),name:(file.name||'粘贴图片').slice(0,120),mimeType:file.type,size:file.size,dataUrl};}));draft.attachments.push(...images);storeAnnotationDraft();}catch(error){ann.error=error.message||'图片读取失败';}finally{ann.adding=false;renderAnnotations();}}
    function annotationDownload(data,type,name){const url=URL.createObjectURL(new Blob([data],{type})),link=document.createElement('a');link.href=url;link.download=name;link.dataset.reviewExport='true';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),5000);}
    async function embeddedAnnotations(){return Promise.all(ann.items.map(async c=>{const embed=async url=>{const response=await fetch(url);if(!response.ok)throw Error('批注图片导出失败');return fileData(await response.blob());};return {...c,attachments:await Promise.all((c.attachments||[]).map(async image=>({...image,dataUrl:image.dataUrl||await embed(image.url)}))),...(c.screenshot&&!c.screenshotData?{screenshotData:await embed(c.screenshot)}:{})};}));}
    async function annotationAction(name,button){
      if(name==='annotation-reload'){maybeReloadAnnotationPage(true);return;}
      if(name==='annotations'){if(ann.open){ann.open=false;renderAnnotations();toolbar();}else openAnnotations();return;}
      if(name==='annotation-close'){if(ann.draft&&!ann.draft.pending&&!ann.draft.text?.trim()&&!ann.draft.attachments?.length){ann.draft=null;ann.shot=null;storeAnnotationDraft();}ann.open=false;ann.selection=null;renderAnnotations();drawAnnotations();toolbar();ui.querySelector('[data-action=annotations]')?.focus();return;}
      if(name==='annotation-create'){
        if(!ann.selection||state.active)return;if(ann.draft){openAnnotations(ann.draft.id);$('annotation-input')?.focus();notice('已恢复未发送的批注；发送后可为新选区添加批注');return;}
        const selected=ann.selection;ann.draft={id:'annotation-'+requestId(),requestId:requestId(),anchor:selected.anchor,page:selected.page,text:'',attachments:[],autoReply:true};
        const draft=ann.draft;ann.shot=(fileMode?Promise.resolve(null):capture()).then(async data=>{if(ann.draft===draft&&data){draft.screenshotData=await markSnapshot(data,draft.anchor.rect);storeAnnotationDraft();}return data;}).catch(error=>{if(ann.draft===draft){ann.error=error.message;renderAnnotations();}return null;});
        ann.selection=null;getSelection()?.removeAllRanges();storeAnnotationDraft();openAnnotations(ann.draft.id);drawAnnotations();$('annotation-input')?.focus();return;
      }
      if(name==='annotation-discard'){if(ann.sending||ann.draft?.pending)return;ann.draft=null;ann.shot=null;storeAnnotationDraft();ann.current=null;ann.draftView=false;ann.error='';renderAnnotations();return;}
      if(name==='annotation-list'){ann.current=null;ann.draftView=false;renderAnnotations();return;}
      if(name==='annotation-draft'){ann.current=ann.draft?.id;ann.draftView=true;renderAnnotations();$('annotation-input')?.focus();return;}
      if(name==='annotation-open'){openAnnotations(button.dataset.id);const target=ann.items.find(c=>c.id===button.dataset.id)||ann.draft;if(target)locateAnnotation(target);return;}
      if(name==='annotation-filter'){ann.filter=button.dataset.filter;ann.current=null;renderAnnotations();drawAnnotations();return;}
      if(name==='annotation-agent-toggle'){const id=ann.current;if(!annotationCanSend()||ann.sending||ann.requests[id+':annotation-message']||ann.draft?.id===id&&ann.draft.pending)return;const value=!annotationReplyPreference(id);if(ann.draft?.id===id){ann.draft.autoReply=value;storeAnnotationDraft();}else{ann.replyAgent[id]=value;annotationStorage('annotationReplyAgent',ann.replyAgent);}renderAnnotations();return;}
      if(name==='annotation-expand'){const key=button.dataset.id+':'+button.dataset.message;ann.expanded[key]=!ann.expanded[key];renderAnnotations();return;}
      if(name==='annotation-prev'||name==='annotation-next'||name==='annotation-nearest'){const records=annotationOrder(annotationVisibleRecords());if(!records.length)return;let i=records.findIndex(c=>c.id===ann.current);if(name==='annotation-nearest'){const distance=record=>{const location=annotationLocation(record.anchor),bounds=location.getBoundingClientRect()||ui.querySelector('.annotation-card[data-id=\"'+CSS.escape(record.id)+'\"]')?.getBoundingClientRect();return bounds?Math.abs(bounds.top-100):Infinity;};i=records.reduce((best,c,index)=>distance(c)<distance(records[best])?index:best,0);}else i=Math.max(0,Math.min(records.length-1,i+(name==='annotation-prev'?-1:1)));openAnnotations(records[i].id);locateAnnotation(records[i]);if(ann.layout==='drawer')ui.querySelector('.annotation-card[data-active=true]')?.scrollIntoView({block:'nearest'});return;}
      if(name==='annotation-return'){const record=currentAnnotation()||ann.draft;await annotationAction('annotation-close');if(record)locateAnnotation(record);return;}
      if(name==='annotation-refresh'){await refreshAnnotations();return;}
      if(name==='annotation-send'||name==='annotation-confirm'){await sendAnnotation();return;}
      if(name==='annotation-add-image'){$('annotation-image-input')?.click();return;}
      if(name==='annotation-remove-image'){if(!ann.draft?.pending){ann.draft.attachments.splice(Number(button.dataset.index),1);storeAnnotationDraft();renderAnnotations();}return;}
      if(name==='annotation-export'){const records=await embeddedAnnotations();annotationDownload('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>页面内容批注 · 离线副本</title><style>body{font:15px/1.7 system-ui;max-width:900px;margin:32px auto;padding:0 20px;color:#202535}article{border-bottom:1px solid #ddd;padding:20px 0}blockquote{border-left:3px solid #98a4bd;margin:12px 0;padding:8px 16px;background:#f5f6f9}p{white-space:pre-wrap;overflow-wrap:anywhere}img{max-width:100%;max-height:480px}small{color:#606879}</style><h1>页面内容批注</h1><p>离线副本，仅含导出时已保存的内容与回复。</p>'+records.map(c=>'<article><h2>#'+c.number+' · '+esc(c.page.title)+'</h2><small>'+esc(c.status)+' · '+esc(c.page.path)+'</small><blockquote>'+esc(c.anchor.selectedText)+'</blockquote><p><b>我：</b>'+esc(c.text)+'</p>'+(c.attachments||[]).map(image=>'<img alt="批注附图" src="'+esc(image.dataUrl)+'">').join('')+(c.screenshotData?'<details><summary>原始截图</summary><img alt="原始截图" src="'+esc(c.screenshotData)+'"></details>':'')+'<small>Agent：'+esc(c.conversation?.status||'无回复')+'</small>'+annotationMessages(c).map(m=>'<p><b>'+(m.role==='user'?'我：':'Agent：')+'</b>'+esc(m.text)+'</p>').join('')+'</article>').join('')+'<script type="application/json" id="annotation-export-data">'+JSON.stringify({format:'prototype-review',version:2,annotations:records}).replace(/</g,'\\u003c')+'</script></html>','text/html','页面内容批注-'+new Date().toISOString().slice(0,10)+'.html');return;}
      const record=button?.dataset.id?ann.items.find(c=>c.id===button.dataset.id):currentAnnotation();
      if(name==='annotation-preview'&&!record&&ann.draft){const image=ann.draft.attachments[Number(button.dataset.index)];if(image){const opened=window.open('','_blank');if(opened){const img=opened.document.createElement('img');img.src=imageSource(image);img.style.maxWidth='100%';opened.document.body.append(img);}}return;}
      if(!record)return;
      if(name==='annotation-locate'){if(pageKey(record.page.path)!==pageKey(location.href)){notice('原文位于 '+record.page.path);return;}locateAnnotation(record);return;}
      if(name==='annotation-preview'||name==='annotation-snapshot'){const image=name==='annotation-snapshot'?record.screenshotData||record.screenshot:imageSource((record.attachments||[])[Number(button.dataset.index)]||{});if(image){const opened=window.open('','_blank');if(opened){opened.document.title='内容批注证据';const img=opened.document.createElement('img');img.src=image;img.style.maxWidth='100%';opened.document.body.append(img);}}return;}
      if(name==='annotation-status'){
        const desiredStatus=button.dataset.status;
        if(endpoint){const response=await fetch(endpoint+'annotations');if(!response.ok)throw Error('读取最新批注失败');const fresh=(await response.json()).annotations.find(c=>c.id===record.id);if(!fresh)throw Error('批注已不存在');const data=await annotationPost('',{annotation:{...fresh,status:desiredStatus},expectedUpdate:fresh.updatedAt});mergeAnnotation(data.annotation);}
        else{const updated={...record,status:desiredStatus,updatedAt:Date.now()};if(!annotationStorage('annotations',ann.items.map(c=>c.id===record.id?updated:c)))throw Error(ann.error);mergeAnnotation(updated);}renderAnnotations();toolbar();drawAnnotations();return;
      }
      if(ann.sending||(name!=='annotation-message'&&!annotationCanSend()))return;
      if(name==='annotation-start'){
        const key=record.id+':start';ann.sending=true;ann.error='';renderAnnotations();
        try{
          let payload=ann.requests[key];
          if(!payload){
            const response=await fetch(endpoint+'annotations');if(!response.ok)throw Error('读取最新批注失败');
            const fresh=(await response.json()).annotations.find(c=>c.id===record.id);if(!fresh)throw Error('批注已不存在');
            const token=ann.requests[record.id+':initial']?.requestId||requestId();
            payload={annotation:fresh,expectedUpdate:fresh.updatedAt,autoReply:true,requestId:token};
            ann.requests[key]=payload;ann.requests[record.id+':initial']={requestId:token};
            if(!annotationStorage('annotationRequests',ann.requests))throw Error(ann.error);
          }
          const data=await annotationPost('',payload);mergeAnnotation(data.annotation);
          if(data.agentError)ann.error='批注已保存，Agent 派发待确认；'+String(data.agentError);
          else{delete ann.requests[key];annotationStorage('annotationRequests',ann.requests);}
        }catch(error){ann.error=error.message||'未收到启动确认，请重试同一条请求';}
        finally{ann.sending=false;renderAnnotations();toolbar();}
        return;
      }
      const requestKey=record.id+':'+name;
      if(name==='annotation-message'||name==='annotation-retry'||name==='annotation-stop'){
        const text=ann.chats[record.id]?.trim()||'';if(name==='annotation-message'&&!text&&!ann.requests[requestKey])return;
        const saved=ann.requests[requestKey];let payload;
        if(name==='annotation-message')payload=saved||{annotationId:record.id,messageId:requestId(),text,autoReply:annotationCanSend()&&annotationReplyPreference(record.id)};else if(name==='annotation-retry')payload=saved||{annotationId:record.id,requestId:requestId()};else payload={annotationId:record.id};
        if(name!=='annotation-stop'){ann.requests[requestKey]=payload;annotationStorage('annotationRequests',ann.requests);}
        ann.sending=true;ann.error='';renderAnnotations();
        try{let conversation;if(endpoint){const data=await annotationPost('/'+({ 'annotation-message':'message','annotation-retry':'retry','annotation-stop':'stop'}[name]),payload);conversation=data.conversation;}else{if(payload.autoReply)throw Error(annotationReason());const existing=record.conversation||{id:record.id,status:'saved',hasAgent:false,messages:[]};const found=(existing.messages||[]).find(m=>m.id===payload.messageId);if(found&&(found.text!==payload.text||found.autoReply!==false))throw Error('该发送请求内容已变化');conversation={...existing,messages:found?existing.messages:[...(existing.messages||[]),{id:payload.messageId,role:'user',text:payload.text,autoReply:false,status:'saved',createdAt:Date.now()/1000}]};const updated={...record,conversation};if(!annotationStorage('annotations',ann.items.map(c=>c.id===record.id?updated:c)))throw Error(ann.error);}record.conversation=conversation;mergeAnnotation(record);delete ann.requests[requestKey];annotationStorage('annotationRequests',ann.requests);if(name==='annotation-message'&&ann.chats[record.id]?.trim()===payload.text){ann.chats[record.id]='';annotationStorage('annotationChats',ann.chats);delete ann.replyAgent[record.id];annotationStorage('annotationReplyAgent',ann.replyAgent);if(ann.current===record.id&&$('annotation-followup'))$('annotation-followup').value='';}}catch(error){ann.error=error.message||'未收到确认，请重试同一条消息';}finally{ann.sending=false;renderAnnotations();}
      }
    }
    function annotationEvent(e,eventPath){
      e.stopImmediatePropagation();const field=eventPath[0],button=eventPath.find(el=>el?.dataset?.action),menu=eventPath.find(el=>el?.matches?.('details.annotation-menu'));
      if(e.type==='pointerdown'&&button?.dataset.action==='annotation-create')e.preventDefault();
      if(e.type==='click'&&button&&!button.disabled){e.preventDefault();if(menu)menu.open=false;annotationAction(button.dataset.action,button).catch(error=>{ann.error=error.message;renderAnnotations();});}
      if(e.type==='click'&&!button&&!menu){const card=eventPath.find(el=>el?.classList?.contains('annotation-card'));if(card&&ann.current!==card.dataset.id&&!getSelection()?.toString()&&!ui.getSelection?.()?.toString()){openAnnotations(card.dataset.id);const record=ann.items.find(c=>c.id===card.dataset.id)||ann.draft;if(record)locateAnnotation(record);}}
      if(e.type==='keydown'&&field.classList?.contains('annotation-card')&&(e.key==='Enter'||e.key===' ')){e.preventDefault();openAnnotations(field.dataset.id);}
      if(e.type==='input'&&['annotation-input','annotation-followup'].includes(field.id)){field.style.height='auto';field.style.height=Math.min(180,Math.max(66,field.scrollHeight))+'px';}
      if(e.type==='input'&&field.id==='annotation-input'&&ann.draft){ann.draft.text=field.value;storeAnnotationDraft();updateAnnotationSend();}
      if(e.type==='input'&&field.id==='annotation-followup'&&ann.current){ann.chats[ann.current]=field.value;annotationStorage('annotationChats',ann.chats);updateAnnotationSend();}
      if(e.type==='change'&&field.id==='annotation-image-input')addAnnotationImages([...field.files]);
      if(e.type==='paste'&&field.id==='annotation-input'){const files=[...(e.clipboardData?.items||[])].filter(item=>item.kind==='file').map(item=>item.getAsFile()).filter(Boolean);if(files.length){e.preventDefault();const text=e.clipboardData.getData('text/plain');if(text){field.setRangeText(text,field.selectionStart,field.selectionEnd,'end');ann.draft.text=field.value;storeAnnotationDraft();}addAnnotationImages(files);}}
      if(e.type==='keydown'){if(e.key==='Escape'){e.preventDefault();annotationAction('annotation-close');}if(['annotation-input','annotation-followup'].includes(field.id)&&e.key==='Enter'&&!e.isComposing&&e.keyCode!==229&&(e.metaKey||e.ctrlKey)){e.preventDefault();annotationAction(field.id==='annotation-followup'?'annotation-message':'annotation-send');}}
    }

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
      const markup = `<div class="bar ${state.active?'active':''}"><button data-action="move-toolbar" class="grip" aria-label="拖动评论工具栏" title="拖动工具栏">⠿</button>${state.active?`<strong><i></i>评论中</strong><div class="modes" aria-label="选区方式">${[['element','点选'],['area','框选'],['text','文字']].map(([v,t])=>`<button data-action="mode" data-mode="${v}" aria-pressed="${state.mode===v}">${t}</button>`).join('')}</div><button data-action="toggle" class="exit">退出评论</button>`:'<button data-action="toggle" class="enter">评论模式</button>'}<button data-action="list" aria-expanded="${state.list}">评论 <span class="count">${n}</span></button><button data-action="annotations" aria-controls="annotation-panel" aria-expanded="${ann.open}">内容批注${ann.refreshPending?' · 有更新':''} <span class="count">${annotationPageRecords().filter(c=>c.status!=='resolved').length}</span></button>${codexEnabled?codexButton():''}</div>${state.active?`<div class="hint">${state.mode==='text'?'拖选文字后添加评论':'点选元素，拖动可框选任意区域'} · Esc 取消选区</div>`:''}`;
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
      return `<button class="codex-launch ${busy?'running':''}" data-action="codex" title="${esc(title)}" aria-expanded="${state.codexPanel}" aria-controls="codex-panel" ${blocked?'disabled':''}>${busy?'<i aria-hidden="true"></i>':''}${busy?`Codex 处理中 ${job.completedCount||0}/${batchComments().length}`:canStart?`交给 Codex · ${pending.length}`:job?`${ended} · 查看结果`:'交给 Codex'}</button>${job&&canStart?`<button class="codex-history" data-action="codex-details" aria-label="继续当前任务对话" title="查看上次任务与对话" aria-expanded="${state.codexPanel}">⌃</button>`:''}<button class="codex-history" data-action="codex-history" aria-label="查看历史评论批次" title="查看历史评论批次" aria-expanded="${state.codexPanel&&state.historyOpen}" aria-controls="codex-panel">历史批次</button>`;
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
      state.codexPanel=open;state.historyOpen=false;state.historyRequest++;
      if(open){ann.open=false;renderAnnotations();}
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
      if(state.historyOpen){renderCodexHistory();return;}
      const job=state.codex,busy=codexBusy(),comments=batchComments(),remaining=job?.pendingCount??comments.length;
      if(!job){panel.innerHTML='';return;}
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
    function historyStatus(job) {
      return {starting:'启动中',running:'处理中',stopping:'停止中',completed:'已完成',failed:'未完成',cancelled:'已停止'}[job.status]||'状态待核对';
    }
    function historyTime(job) {
      return job.startedAt?new Date(job.startedAt*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'时间未记录';
    }
    function renderCodexHistory() {
      const panel=$('codex-panel'),revision=String(state.historyRevision);
      if(panel.firstElementChild?.dataset.history===revision){positionCodex();return;}
      const job=state.historyJob,data=state.historyData;
      let content='';
      if(state.historyLoading)content='<p role="status">正在读取历史批次…</p>';
      else if(state.historyError)content=`<p class="error" role="alert">${esc(state.historyError)}</p><button data-action="codex-history">重新读取</button>`;
      else if(job){
        const messages=job.messages?.length?job.messages:job.result?[{role:'assistant',text:job.result}]:[];
        content=`<p class="codex-summary">${esc(historyTime(job))} · ${esc(historyStatus(job))}</p><p class="codex-history-subject">${esc(job.title)}</p><div class="codex-thread" role="log" aria-label="历史任务对话">${messages.filter(m=>m.text).map(m=>`<article class="codex-message ${m.role==='user'?'from-user':'from-agent'}"><div class="codex-message-meta"><small>${m.role==='user'?'你':'Codex'}</small></div><p>${esc(m.text)}</p></article>`).join('')||'<p>此任务没有保存对话消息。</p>'}</div>${job.result?`<details class="codex-records"><summary>最终处理结果</summary><p class="codex-history-result">${esc(job.result)}</p></details>`:''}${job.error?`<p class="error">${esc(job.error)}</p>`:''}<details class="codex-records"><summary>本批评论 ${(job.comments||[]).length}</summary><ol class="codex-comments">${(job.comments||[]).map(c=>`<li><span>#${esc(c.number)} ${esc(c.text||'图片评论')}</span></li>`).join('')}</ol></details><button data-action="codex-history" data-offset="${data?.offset||0}">返回批次列表</button>`;
      }else{
        content=`<div class="codex-history-list">${(data?.jobs||[]).map(j=>`<button class="codex-history-row" data-action="codex-history-job" data-job-id="${esc(j.id)}"><span>${esc(j.title)}</span><small>${esc(historyTime(j))} · ${esc(historyStatus(j))}${j.id===data.currentId?' · 当前批次':''}</small></button>`).join('')||'<p>暂无历史评论批次。</p>'}</div><div class="codex-history-pages"><span>共 ${data?.total||0} 个批次</span><div>${data?.offset?`<button data-action="codex-history" data-offset="${Math.max(0,data.offset-20)}">上一页</button>`:''}${data?.nextOffset!=null?`<button data-action="codex-history" data-offset="${data.nextOffset}">下一页</button>`:''}</div></div>`;
      }
      panel.innerHTML=`<section class="panel codex-task" data-history="${revision}" role="dialog" aria-label="历史评论批次"><header><div><small>本机 Codex</small><strong>历史评论批次</strong></div><button data-action="codex-close" aria-label="收起历史批次">⌄</button></header>${content}<footer><span>历史记录仅供查看</span>${state.codex?'<button data-action="codex-details">返回当前任务</button>':''}</footer></section>`;
      positionCodex();
    }
    async function loadCodexHistory(identity=null,offset=0) {
      if(!codexEnabled)return;
      if(!state.codexPanel||!state.historyOpen)showCodex(true);
      state.historyOpen=true;state.historyJob=null;state.historyLoading=true;state.historyError='';state.historyRevision++;
      const token=++state.historyRequest;renderCodex();
      try{
        const path=identity?'codex/history/'+encodeURIComponent(identity):'codex/history?offset='+offset+'&limit=20';
        const response=await fetch(endpoint+path),data=await response.json();
        if(!response.ok)throw Error(data.error||'历史任务读取失败');
        if(token!==state.historyRequest||!state.historyOpen)return;
        if(identity)state.historyJob=data.job;
        else state.historyData={...data,offset};
      }catch(error){if(token===state.historyRequest)state.historyError=error.message;}
      finally{if(token===state.historyRequest){state.historyLoading=false;state.historyRevision++;renderCodex();}}
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
      if(active){ann.selection=null;ann.open=false;renderAnnotations();drawAnnotations();}
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
      if(name==='annotations'||name.startsWith('annotation-')){await annotationAction(name,button);return;}
      const comment=state.items.find(c=>c.id===button?.dataset.id);
      if(state.saving && !['list'].includes(name)||state.adding&&!['list','cancel'].includes(name))return;
      if(name==='codex')await startCodex();
      if(name==='codex-retry')await startCodex(button.dataset.id);
      if(name==='codex-close'){showCodex(false);ui.querySelector('[data-action=codex]')?.focus();}
      if(name==='codex-history'){await loadCodexHistory(null,Number(button.dataset.offset)||0);}
      if(name==='codex-history-job'){await loadCodexHistory(button.dataset.jobId);}
      if(name==='codex-details')showCodex(state.historyOpen||!state.codexPanel);
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
      if(name==='list'){ann.open=false;renderAnnotations();state.list=!state.list;if(state.list){state.codexPanel=false;renderCodex();}renderList();toolbar();draw();}
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
        const blob=new Blob([JSON.stringify({format:'prototype-review',version:2,comments:copy,annotations:await embeddedAnnotations()},null,2)],{type:'application/json'});
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
      syncAnnotationIdentity();
      observeAnnotationEditing(e,eventPath);
      if(eventPath.some(el=>el?.dataset?.reviewExport))return;
      if(e.type==='click')closeAnnotationMenus(eventPath.find(el=>el?.matches?.('details.annotation-menu')));
      if(e.type==='keydown'&&e.key==='Escape'&&closeAnnotationMenus(null,true)){e.preventDefault();e.stopImmediatePropagation();return;}
      if(state.drag?.toolbar&&e.type==='pointermove'){
        e.preventDefault();e.stopImmediatePropagation();const d=state.drag;
        $('toolbar').style.cssText=`left:${Math.max(0,Math.min(innerWidth-$('toolbar').offsetWidth,d.left+e.clientX-d.x))}px;top:${Math.max(0,Math.min(innerHeight-90,d.top+e.clientY-d.y))}px;bottom:auto;transform:none;`;positionCodex();return;
      }
      if(state.drag?.toolbar&&e.type==='pointerup'){e.preventDefault();e.stopImmediatePropagation();state.drag=null;return;}
      const own=eventPath.includes(host);
      if(own&&eventPath.some(el=>['annotation-panel','annotation-selection','annotation-highlights'].includes(el?.id))){annotationEvent(e,eventPath);return;}
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
      if(!state.active){
        if(e.type==='pointerdown'&&e.button===0)ann.pointer={x:e.clientX,y:e.clientY};
        if(e.type==='click'&&ann.pointer){const pointer=ann.pointer;ann.pointer=null;if(Math.hypot(e.clientX-pointer.x,e.clientY-pointer.y)<5&&!getSelection()?.toString()&&!e.target.closest?.('a,button,input,textarea,select,[contenteditable]')){const matches=annotationVisibleRecords().filter(c=>{const r=restoreAnnotationRange(c.anchor);return r&&[...r.getClientRects()].some(b=>e.clientX>=b.left&&e.clientX<=b.right&&e.clientY>=b.top&&e.clientY<=b.bottom);});if(matches.length){const chosen=matches.find(c=>c.id===ann.current)||matches.find(c=>c.id===ann.lastAnchor)||matches[0];ann.lastAnchor=chosen.id;openAnnotations(chosen.id);}else if(ann.open&&ann.current){ann.current=null;renderAnnotations();drawAnnotations();}}}
        if(e.type==='pointerup'||e.type==='keyup')scheduleAnnotationSelection();
        if(e.type==='keydown'&&e.key==='Escape'){if(ann.open){e.preventDefault();annotationAction('annotation-close');}else if(ann.selection){ann.selection=null;getSelection()?.removeAllRanges();drawAnnotations();}}
        return;
      }
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
    window.addEventListener('scroll',()=>{draw();drawAnnotations();},true);
    window.addEventListener('resize',()=>{editor();draw();positionCodex();if(ann.open){const previous=ann.layout;syncAnnotationLayout();renderAnnotations();if(previous!=='drawer'&&ann.layout==='drawer')requestAnimationFrame(()=>ui.querySelector('.annotation-card[data-active=true] .annotation-compose')?.scrollIntoView({block:'end'}));}drawAnnotations();});
    new ResizeObserver(()=>{if(ann.open)layoutAnnotationCards();}).observe($('annotation-panel'));
    new ResizeObserver(positionCodex).observe($('toolbar'));
    new ResizeObserver(positionCodex).observe($('codex-panel'));
    let drawing=false;
    new MutationObserver(()=>{if(drawing)return;drawing=true;requestAnimationFrame(()=>{drawing=false;draw();drawAnnotations();});}).observe(document.body,{subtree:true,attributes:true,childList:true,characterData:true});
    window.addEventListener('blur',()=>{state.drag=null;});
    window.PrototypeReview={version:1};
    window.addEventListener('pagehide',saveAnnotationView);
    let viewSaveQueued=false;
    window.addEventListener('scroll',()=>{if(!viewSaveQueued){viewSaveQueued=true;requestAnimationFrame(()=>{viewSaveQueued=false;saveAnnotationView();});}},{capture:true,passive:true});
    window.addEventListener('compositionstart',()=>{ann.composing=true;},true);
    window.addEventListener('compositionend',()=>{ann.composing=false;},true);
    toolbar();refresh();refreshAnnotations();renderAnnotations();
    document.addEventListener('selectionchange',scheduleAnnotationSelection);
    let annotationSyncing=false;
    const annotationSync=async()=>{if(annotationSyncing||document.hidden)return;annotationSyncing=true;try{await refreshAnnotations();}finally{annotationSyncing=false;}};
    setInterval(annotationSync,1500);window.addEventListener('focus',annotationSync);
    window.addEventListener('hashchange',annotationSync);window.addEventListener('popstate',annotationSync);
    document.addEventListener('visibilitychange',annotationSync);
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
