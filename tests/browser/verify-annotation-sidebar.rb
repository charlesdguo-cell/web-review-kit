require_relative '../support/browser'

# Only test_annotations_browser.py creates these services and files. No retained
# consumer service, annotation or Codex account is involved.
root = File.expand_path('../..', __dir__)
out = File.join(root, 'artifacts/validation-annotation-sidebar')
FileUtils.mkdir_p(out)
fixture = ENV.fetch('ANNOTATIONS_FIXTURE')
legacy_bytes = File.binread(File.join(fixture,'data/comments.json'))
base = ENV.fetch('ANNOTATIONS_TEST_URL')
ui = "document.querySelector('#prototype-review').shadowRoot"
b = PrototypeBrowser.new
c = b.cdp
checks = []
check = lambda { |name, expression| raise name unless c.evaluate(expression); checks << name; puts "PASS #{name}" }
ready = lambda do
  c.wait_for("!!window.PrototypeReview&&!!#{ui}.querySelector('[data-action=annotations]')")
  c.wait_for("!!#{ui}.querySelector('link').sheet")
end
click = lambda do |selector|
  xy = c.evaluate("(async()=>{const e=#{ui}.querySelector(#{selector.to_json});if(!e)throw Error('Missing '+#{selector.to_json});e.scrollIntoView({block:'nearest'});let r=e.getBoundingClientRect();if(#{ui}.querySelector('.annotation-sidebar')?.dataset.layout==='aligned'&&r.bottom>innerHeight-20){scrollBy(0,r.bottom-innerHeight+80);await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);r=e.getBoundingClientRect()}return{x:r.x+r.width/2,y:r.y+r.height/2}})()")
  c.call('Input.dispatchMouseEvent', type:'mousePressed', x:xy['x'], y:xy['y'], button:'left', clickCount:1)
  c.call('Input.dispatchMouseEvent', type:'mouseReleased', x:xy['x'], y:xy['y'], button:'left', clickCount:1)
end
# Offscreen layout assertions activate with the same public button handler,
# without scrollIntoView changing the document coordinates under measurement.
activate = lambda do |id|
  c.wait_for("!!#{ui}.querySelector('.annotation-card[data-id=\"#{id}\"] [data-action=annotation-open]')")
  c.evaluate("#{ui}.querySelector('.annotation-card[data-id=\"#{id}\"] [data-action=annotation-open]').click()")
  c.wait_for("#{ui}.querySelector('.annotation-card[data-id=\"#{id}\"] #annotation-followup')")
  sleep 0.2
end
fill = lambda do |selector, value|
  c.evaluate("(()=>{const e=#{ui}.querySelector(#{selector.to_json});e.focus();e.select()})()")
  c.call('Input.insertText', text:value)
end
key = lambda do |name|
  code = {'Escape'=>27, 'Enter'=>13}.fetch(name)
  c.call('Input.dispatchKeyEvent', type:'keyDown', key:name, code:name, windowsVirtualKeyCode:code)
  c.call('Input.dispatchKeyEvent', type:'keyUp', key:name, code:name, windowsVirtualKeyCode:code)
end
rpc = lambda do |method|
  path = File.join(fixture, 'rpc.jsonl')
  File.exist?(path) ? File.readlines(path).map { |line| JSON.parse(line) }.count { |row| row['method'] == method } : 0
end
get = "fetch('/__review/annotations').then(r=>r.json()).then(d=>d.annotations)"
geometry = "(()=>{const r={scrollY,header:#{ui}.querySelector('.annotation-sidebar header').getBoundingClientRect().top};for(const id of ['first','adjacent','overlap-a','overlap-b','middle','last']){const card=#{ui}.querySelector('.annotation-card[data-id=\"annotation-'+id+'\"]');if(card){const q=card.getBoundingClientRect();r[id]={top:q.top,bottom:q.bottom,height:q.height}}}r.text=document.querySelector('#middle').getBoundingClientRect().top;return r})()"
begin
  $stdout.sync = true
  c.call('Emulation.setDeviceMetricsOverride', width:1440, height:1000, deviceScaleFactor:1, mobile:false)
  c.call('Page.navigate', url:base)
  ready.call
  c.evaluate(<<~JS)
    (async()=>{window.originalBodyStyle=document.body.getAttribute('style');
    const rows=[['first','#first',0,23],['adjacent','#adjacent',0,26],['overlap-a','#overlap',0,24],['overlap-b','#overlap',12,38],['resolved','#resolved',0,26],['middle','#middle',0,24],['last','#last',0,22],['other','#first',0,23]];
    for(const [name,selector,start,end] of rows){const el=document.querySelector(selector),text=el.textContent,exact=text.slice(start,end);
    const record={id:'annotation-'+name,text:'Synthetic note '+name,status:name==='resolved'?'resolved':'open',page:{path:name==='other'?'/other.html':'/',title:'Synthetic reading'},
    screenshotData:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLttAAAAABJRU5ErkJggg==',anchor:{kind:'text',selector,selectedText:exact,textRange:{start,end,exact,prefix:text.slice(Math.max(0,start-40),start),suffix:text.slice(end,end+40)}},attachments:[]};
    const response=await fetch('/__review/annotations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({annotation:record,autoReply:false})});if(!response.ok)throw Error(await response.text());}
    })()
  JS
  # A long synthetic historical Agent reply exercises expansion only. This is
  # public fixture data, never a worker snapshot from another project.
  long_text = (1..24).map { |n| "Synthetic reply line #{n}: explains the selected original sentence." }.join("\n")
  thread_dir = File.join(fixture, 'data/annotation-threads')
  FileUtils.mkdir_p(thread_dir)
  File.write(File.join(thread_dir, 'annotation-first.json'), JSON.generate(id:'annotation-first',status:'completed',canChat:true,
    messages:[{id:'synthetic-long',role:'assistant',text:long_text,status:'sent',createdAt:1}],result:long_text))
  c.call('Page.reload')
  ready.call
  c.wait_for("#{ui}.querySelector('[data-action=annotations]').textContent.includes('6')")
  c.evaluate('scrollTo(0,520)')
  sleep 0.2
  original_body_style = c.evaluate("document.body.getAttribute('style')")
  c.evaluate("window.beforeOpenY=scrollY;window.originalBodyStyle=document.body.getAttribute('style')")
  click.call('[data-action=annotations]')
  c.wait_for("#{ui}.querySelectorAll('.annotation-card').length===6")
  check.call('Current-page open count excludes other-page records and default filter excludes resolved', "#{ui}.querySelector('[data-action=annotations]').textContent.includes('6')&&!#{ui}.querySelector('.annotation-card[data-id=annotation-other]')&&!#{ui}.querySelector('.annotation-card[data-id=annotation-resolved]')")
  check.call('Opening ordinary document reserves 320px without transforming or wrapping body', "Math.abs(parseFloat(getComputedStyle(document.body).paddingRight)-327)<1&&getComputedStyle(document.body).transform==='none'&&document.querySelector('main').parentElement===document.body&&Math.abs(scrollY-window.beforeOpenY)<80")
  c.evaluate('scrollTo(0,0)')
  sleep 0.2
  # Native details.open and keyboard focus are UI state. Successful background
  # annotation reads must not replace the menu with its original closed markup.
  c.evaluate(<<~JS)
    window.menuFetch=window.fetch;window.annotationPolls=0;
    window.fetch=async(...args)=>{const response=await window.menuFetch(...args);
      if(new URL(String(args[0]),location.href).pathname==='/__review/annotations'&&(!args[1]?.method||args[1].method==='GET')){
        const json=response.json.bind(response);response.json=async()=>{const data=await json();requestAnimationFrame(()=>requestAnimationFrame(()=>window.annotationPolls++));return data;};
      }return response;};
  JS
  activate.call('annotation-adjacent')
  card_menu = '.annotation-card[data-id=annotation-adjacent] .annotation-menu'
  click.call(card_menu+' summary')
  c.wait_for("#{ui}.querySelector(#{card_menu.to_json}).open")
  c.evaluate("window.retainedMenu=#{ui}.querySelector(#{card_menu.to_json});window.retainedMenuButton=window.retainedMenu.querySelector('[data-action=annotation-snapshot]');window.retainedMenuButton.focus();window.menuPollStart=window.annotationPolls")
  c.wait_for('window.annotationPolls>=window.menuPollStart+2')
  check.call('Active annotation menu stays open with the same focused control across two background polls', "#{ui}.querySelector(#{card_menu.to_json})===window.retainedMenu&&window.retainedMenu.open&&window.retainedMenu.contains(window.retainedMenuButton)&&#{ui}.activeElement===window.retainedMenuButton")
  # Only this temporary fixture snapshot changes: no worker or real task is
  # created. Polling must still paint streaming text next to the open menu.
  streaming_path = File.join(thread_dir, 'annotation-adjacent.json')
  ['Synthetic streaming reply.', 'Synthetic streaming reply. A second delta arrived.'].each do |text|
    File.write(streaming_path, JSON.generate(id:'annotation-adjacent',status:'running',canChat:true,
      messages:[{id:'synthetic-menu-stream',role:'assistant',text:text,status:'streaming',createdAt:2}]))
    c.wait_for("#{ui}.querySelector('.annotation-card[data-id=annotation-adjacent] [data-part=thread]').textContent.includes(#{text.to_json})")
  end
  check.call('Streaming thread deltas update without replacing or closing the focused annotation menu', "#{ui}.querySelector(#{card_menu.to_json})===window.retainedMenu&&window.retainedMenu.open&&#{ui}.activeElement===window.retainedMenuButton&&#{ui}.querySelector('.annotation-card[data-id=annotation-adjacent] [data-part=state]').textContent.includes('Agent 回复中')")
  FileUtils.rm_f(streaming_path)
  # An actual optimistic metadata update is stronger than an unchanged poll:
  # the new badge must appear while the existing menu and focus remain intact.
  update_menu_status = lambda do |status|
    c.evaluate(<<~JS)
      (async()=>{const read=await window.menuFetch('/__review/annotations'),data=await read.json(),annotation=data.annotations.find(x=>x.id==='annotation-adjacent');
      const response=await window.menuFetch('/__review/annotations',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({annotation:{...annotation,status:#{status.to_json}},expectedUpdate:annotation.updatedAt})});if(!response.ok)throw Error(await response.text());return(await response.json()).annotation;})()
    JS
  end
  update_menu_status.call('changed')
  c.wait_for("(()=>{const badge=#{ui}.querySelector('.annotation-card[data-id=annotation-adjacent] .annotation-changed');return badge&&!badge.hidden&&badge.textContent==='待验收'})()")
  check.call('Metadata status changes render while preserving the open menu and focused action', "#{ui}.querySelector(#{card_menu.to_json})===window.retainedMenu&&window.retainedMenu.open&&#{ui}.activeElement===window.retainedMenuButton")
  update_menu_status.call('open')
  c.wait_for("(()=>{const badge=#{ui}.querySelector('.annotation-card[data-id=annotation-adjacent] .annotation-changed');return(!badge||badge.hidden)&&#{ui}.querySelector('.annotation-card[data-id=annotation-adjacent] [data-part=thread]').textContent===''})()")
  click.call(card_menu+' summary')
  check.call('Clicking the same ellipsis again deliberately closes its menu', "!window.retainedMenu.open&&!!#{ui}.querySelector('.annotation-card[data-id=annotation-adjacent] #annotation-followup')")
  click.call(card_menu+' summary')
  c.wait_for('window.retainedMenu.open')
  c.evaluate('window.retainedMenuButton.focus()')
  key.call('Escape')
  check.call('Escape closes only the menu with focus restored to its summary', "!window.retainedMenu.open&&#{ui}.activeElement===window.retainedMenu.querySelector('summary')&&!!#{ui}.querySelector('.annotation-card[data-id=annotation-adjacent] #annotation-followup')")
  inactive_menu = '.annotation-card[data-id=annotation-overlap-a] .annotation-menu'
  c.evaluate("(async()=>{#{ui}.querySelector(#{(inactive_menu+' summary').to_json}).scrollIntoView({block:'nearest'});await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);window.menuScrollY=scrollY;window.menuActiveField=#{ui}.querySelector('#annotation-followup')})()")
  click.call(inactive_menu+' summary')
  c.wait_for("#{ui}.querySelector(#{inactive_menu.to_json}).open")
  check.call('Inactive card ellipsis opens without activating its card or moving the original text', "!#{ui}.querySelector('.annotation-card[data-id=annotation-overlap-a]').classList.contains('active')&&#{ui}.querySelector('#annotation-followup')===window.menuActiveField&&Math.abs(scrollY-window.menuScrollY)<1")
  c.evaluate("window.inactiveMenu=#{ui}.querySelector(#{inactive_menu.to_json});window.inactiveAction=window.inactiveMenu.querySelector('[data-action=annotation-snapshot]');window.inactiveAction.focus();window.menuPollStart=window.annotationPolls")
  c.wait_for('window.annotationPolls>=window.menuPollStart+2')
  check.call('Inactive card menu and its focused action survive two background polls', "#{ui}.querySelector(#{inactive_menu.to_json})===window.inactiveMenu&&window.inactiveMenu.open&&#{ui}.activeElement===window.inactiveAction&&#{ui}.querySelector('#annotation-followup')===window.menuActiveField")
  key.call('Escape')
  header_menu = '.annotation-sidebar header .annotation-menu'
  click.call(header_menu+' summary')
  c.wait_for("#{ui}.querySelector(#{header_menu.to_json}).open")
  c.evaluate("window.headerMenu=#{ui}.querySelector(#{header_menu.to_json});window.headerAction=window.headerMenu.querySelector('[data-filter=all]');window.headerAction.focus();window.menuPollStart=window.annotationPolls")
  c.wait_for('window.annotationPolls>=window.menuPollStart+2')
  check.call('Header options retain their open menu and focused action across two background polls', "#{ui}.querySelector(#{header_menu.to_json})===window.headerMenu&&window.headerMenu.open&&#{ui}.activeElement===window.headerAction")
  click.call(header_menu+' [data-filter=all]')
  check.call('Choosing a menu action closes it and applies the requested filter', "!window.headerMenu.open&&#{ui}.querySelectorAll('.annotation-card').length===7")
  # Hold only this explicit status action's read. Another optimistic update and
  # a background poll change the stable button's label before that read resumes.
  click.call(card_menu+' summary')
  c.wait_for("#{ui}.querySelector(#{card_menu.to_json}).open")
  c.evaluate(<<~JS)
    window.menuPollingFetch=window.fetch;window.statusActionReadWaiting=false;window.statusActionWrite=null;window.statusActionDone=false;
    window.fetch=async(...args)=>{const annotation=new URL(String(args[0]),location.href).pathname==='/__review/annotations',method=args[1]?.method||'GET';
      if(annotation&&method==='GET'&&window.holdStatusActionRead){window.holdStatusActionRead=false;window.statusActionReadWaiting=true;await new Promise(resolve=>window.releaseStatusActionRead=resolve);}
      if(annotation&&method==='POST')window.statusActionWrite=JSON.parse(args[1].body);
      const response=await window.menuPollingFetch(...args);if(annotation&&method==='POST')window.statusActionDone=true;return response;};
    window.statusActionButton=#{ui}.querySelector(#{(card_menu+' [data-action=annotation-status]').to_json});
    window.holdStatusActionRead=true;window.statusActionButton.click();
  JS
  c.wait_for('window.statusActionReadWaiting')
  externally_resolved = update_menu_status.call('resolved')
  c.wait_for("window.statusActionButton.dataset.status==='open'&&window.statusActionButton.textContent==='重新打开'")
  c.evaluate('window.releaseStatusActionRead()')
  c.wait_for('window.statusActionDone')
  check.call('Status action preserves clicked intent when polling changes its button during the fresh read', "window.statusActionWrite.annotation.status==='resolved'&&window.statusActionWrite.expectedUpdate===#{externally_resolved.fetch('updatedAt').to_json}&&#{ui}.querySelector(#{(card_menu+' [data-action=annotation-status]').to_json})===window.statusActionButton&&!#{ui}.querySelector(#{card_menu.to_json}).open")
  c.evaluate('window.fetch=window.menuPollingFetch')
  update_menu_status.call('open')
  c.wait_for("window.statusActionButton.dataset.status==='resolved'")
  click.call(header_menu+' summary')
  click.call(header_menu+' [data-filter=open]')
  c.wait_for("#{ui}.querySelectorAll('.annotation-card').length===6")
  click.call(card_menu+' summary')
  c.wait_for("#{ui}.querySelector(#{card_menu.to_json}).open")
  c.evaluate('scrollTo(0,0)')
  c.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
  outside = c.evaluate("(()=>{const r=document.querySelector('h1').getBoundingClientRect();return{x:r.left+12,y:r.top+12}})()")
  c.call('Input.dispatchMouseEvent',type:'mousePressed',x:outside['x'],y:outside['y'],button:'left',clickCount:1)
  c.call('Input.dispatchMouseEvent',type:'mouseReleased',x:outside['x'],y:outside['y'],button:'left',clickCount:1)
  check.call('Pointer click outside the menu closes it while leaving the annotation sidebar available', "!#{ui}.querySelector('.annotation-menu[open]')&&!!#{ui}.querySelector('.annotation-sidebar')")
  c.evaluate('window.fetch=window.menuFetch;scrollTo(0,0)')
  activate.call('annotation-adjacent')
  c.evaluate("window.adjacentGeometry=#{geometry}")
  check.call('Active adjacent card aligns to its quote and predecessors avoid upward', "(()=>{const g=window.adjacentGeometry,q=document.querySelector('#adjacent').getBoundingClientRect();return Math.abs(g.adjacent.top-q.top)<30&&g.first.bottom+15<=g.adjacent.top&&g.adjacent.bottom+15<=g['overlap-a'].top})()")
  b.screenshot(File.join(out, 'adjacent-active.png'))
  activate.call('annotation-first')
  c.evaluate("window.firstGeometry=#{geometry}")
  check.call('Switching adjacent card gives current anchor priority rather than downward-only stacking', "window.firstGeometry.first.top>window.adjacentGeometry.first.top+40&&Math.abs(window.firstGeometry.first.top-document.querySelector('#first').getBoundingClientRect().top)<30")
  b.screenshot(File.join(out, 'desktop-cards.png'))
  click.call('[data-action=annotation-expand]')
  sleep 0.2
  c.evaluate("window.longGeometry=#{geometry}")
  check.call('Long reply expands in place and shifts neighbors without moving original text', "window.longGeometry.first.height>window.firstGeometry.first.height+150&&window.longGeometry.adjacent.top>=window.longGeometry.first.bottom+15&&window.longGeometry.scrollY===window.firstGeometry.scrollY")
  b.screenshot(File.join(out, 'long-reply.png'))
  activate.call('annotation-adjacent')
  check.call('A neighbor regains quote alignment after a long thread grows', "Math.abs(#{ui}.querySelector('.annotation-card[data-id=annotation-adjacent]').getBoundingClientRect().top-document.querySelector('#adjacent').getBoundingClientRect().top)<30")
  activate.call('annotation-overlap-b')
  check.call('Overlapping quotations retain independent ordered cards and active composer', "(()=>{const a=#{ui}.querySelector('.annotation-card[data-id=annotation-overlap-a]'),b=#{ui}.querySelector('.annotation-card[data-id=annotation-overlap-b]');return a&&b&&a.getBoundingClientRect().bottom+15<=b.getBoundingClientRect().top&&b.contains(#{ui}.querySelector('#annotation-followup'))&&#{ui}.querySelectorAll('#annotation-followup').length===1})()")
  # Keep a far card active so no collision-height change affects the movement.
  activate.call('annotation-middle')
  c.evaluate("document.querySelector('#middle').scrollIntoView({block:'center'});getSelection().removeAllRanges()")
  sleep 0.3
  before_scroll = c.evaluate(geometry)
  c.evaluate('scrollBy(0,300)')
  sleep 0.3
  after_scroll = c.evaluate(geometry)
  moved_text = before_scroll['text'] - after_scroll['text']
  moved_card = before_scroll['middle']['top'] - after_scroll['middle']['top']
  raise 'Cards failed native main scroll movement' unless (moved_text-300).abs < 2 && (moved_card-300).abs < 2 && (before_scroll['header']-after_scroll['header']).abs < 1
  checks << 'Native document scroll moves original text and card equally by 300px with fixed header'
  check.call('Normal cards have no nested scrolling container', "[...#{ui}.querySelectorAll('.annotation-card')].every(e=>!['auto','scroll'].includes(getComputedStyle(e).overflowY))")
  c.evaluate('scrollTo(0,3100)')
  sleep 0.3
  c.wait_for("!!#{ui}.querySelector('[data-action=annotation-nearest]')")
  click.call('[data-action=annotation-nearest]')
  check.call('Empty viewport offers nearest-annotation jump and reaches original text', 'Math.abs(scrollY-3100)>100')
  c.evaluate("#{ui}.querySelector('[data-action=annotation-filter][data-filter=all]').click()")
  c.wait_for("#{ui}.querySelectorAll('.annotation-card').length===7")
  check.call('All filter exposes resolved records only from current page', "!!#{ui}.querySelector('.annotation-card[data-id=annotation-resolved]')&&!#{ui}.querySelector('.annotation-card[data-id=annotation-other]')")
  c.evaluate("#{ui}.querySelector('[data-action=annotation-filter][data-filter=resolved]').click()")
  c.wait_for("#{ui}.querySelectorAll('.annotation-card').length===1")
  check.call('Resolved filter keeps the saved resolved thread accessible', "!!#{ui}.querySelector('.annotation-card[data-id=annotation-resolved]')")
  c.evaluate("#{ui}.querySelector('[data-action=annotation-filter][data-filter=open]').click();scrollTo(0,0)")
  sleep 0.2
  activate.call('annotation-first')
  check.call('Document-order navigation disables previous at the first annotation', "#{ui}.querySelector('[data-action=annotation-prev]').disabled")
  click.call('[data-action=annotation-next]')
  check.call('Next navigation follows original text order', "!!#{ui}.querySelector('.annotation-card[data-id=annotation-adjacent] #annotation-followup')")
  activate.call('annotation-last')
  check.call('Document-order navigation disables next at the last annotation', "#{ui}.querySelector('[data-action=annotation-next]').disabled")
  c.evaluate('scrollTo(0,0)')
  activate.call('annotation-adjacent')
  fill.call('#annotation-followup', 'Draft for adjacent card.')
  activate.call('annotation-overlap-a')
  fill.call('#annotation-followup', 'Draft for overlapping card.')
  activate.call('annotation-adjacent')
  check.call('Switching cards restores each composer draft', "#{ui}.querySelector('#annotation-followup').value==='Draft for adjacent card.'")
  c.evaluate("window.retainedField=#{ui}.querySelector('#annotation-followup');window.retainedField.focus();window.retainedField.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}))")
  sleep 2.2
  check.call('Polling retains per-card draft, IME field identity and focus', "#{ui}.querySelector('#annotation-followup')===window.retainedField&&#{ui}.activeElement===window.retainedField&&window.retainedField.value==='Draft for adjacent card.'")
  c.evaluate("window.retainedField.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true}))")
  click.call('[data-action=annotation-close]')
  check.call('Closing restores the exact preexisting body inline style', "document.body.getAttribute('style')===window.originalBodyStyle")
  # Existing underlines must not eat pointer text selection or page controls.
  c.evaluate('scrollTo(0,0)')
  points = c.evaluate("(()=>{const n=document.querySelector('#first').firstChild,a=document.createRange(),z=document.createRange();a.setStart(n,0);a.setEnd(n,1);z.setStart(n,19);z.setEnd(n,20);const x=a.getBoundingClientRect(),y=z.getBoundingClientRect();return{ax:x.left+1,ay:x.top+x.height/2,zx:y.right-1,zy:y.top+y.height/2}})()")
  c.call('Input.dispatchMouseEvent',type:'mousePressed',x:points['ax'],y:points['ay'],button:'left',buttons:1,clickCount:1)
  12.times do |n|
    c.call('Input.dispatchMouseEvent',type:'mouseMoved',x:points['ax']+(points['zx']-points['ax'])*(n+1)/12.0,y:points['zy'],button:'left',buttons:1)
  end
  c.call('Input.dispatchMouseEvent',type:'mouseReleased',x:points['zx'],y:points['zy'],button:'left',clickCount:1)
  c.wait_for("getSelection().toString().includes('First original')")
  check.call('Annotated original text remains natively selectable', "getSelection().toString().includes('First original')")
  c.evaluate('getSelection().removeAllRanges()')
  c.call('Input.dispatchMouseEvent',type:'mousePressed',x:points['ax']+25,y:points['ay'],button:'left',clickCount:1)
  c.call('Input.dispatchMouseEvent',type:'mouseReleased',x:points['ax']+25,y:points['ay'],button:'left',clickCount:1)
  c.wait_for("!!#{ui}.querySelector('.annotation-card[data-id=annotation-first] #annotation-followup')")
  check.call('Pointer click on annotated original activates its associated card', "!!#{ui}.querySelector('.annotation-card[data-id=annotation-first].active')")
  c.evaluate('document.querySelector("#ordinary").click()')
  check.call('Ordinary page controls remain usable outside review mode', "window.pageActions===1&&!document.documentElement.hasAttribute('data-prototype-review-active')")
  # New root and followup both off: save, never launch or backfill.
  c.evaluate(<<~JS)
    (()=>{const n=document.querySelector('#middle').firstChild,r=document.createRange();r.setStart(n,7);r.setEnd(n,24);getSelection().removeAllRanges();getSelection().addRange(r);document.querySelector('#middle').scrollIntoView({block:'center'});document.dispatchEvent(new Event('selectionchange'));document.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}))})()
  JS
  c.wait_for("!!#{ui}.querySelector('[data-action=annotation-create]')")
  click.call('[data-action=annotation-create]')
  c.wait_for("!!#{ui}.querySelector('#annotation-input')")
  check.call('Each new local composer defaults Agent response on', "#{ui}.querySelector('#annotation-agent-toggle').getAttribute('aria-checked')==='true'")
  fill.call('#annotation-input', 'Initial saved note without Agent.')
  click.call('#annotation-agent-toggle')
  before = rpc.call('turn/start')
  click.call('[data-action=annotation-send]')
  c.wait_for("!!#{ui}.querySelector('#annotation-followup')",30)
  note_id = c.evaluate("#{get}.then(a=>a.find(x=>x.text==='Initial saved note without Agent.').id)")
  check.call('Agent off initial message is saved without queuing', "#{get}.then(a=>{const x=a.find(x=>x.id===#{note_id.to_json});return x&&!['queued','running','starting'].includes(x.conversation?.status)})")
  # Followup has its own choice, and off never disables saving.
  click.call('#annotation-agent-toggle') if c.evaluate("#{ui}.querySelector('#annotation-agent-toggle').getAttribute('aria-checked')==='true'")
  fill.call('#annotation-followup', 'Saved followup context only.')
  c.evaluate("window.realFetch=fetch;window.dropSavedReply=true;window.pendingBodies=[];window.fetch=async(...args)=>{const res=await window.realFetch(...args);if(String(args[0]).endsWith('/annotations/message')&&args[1]?.method==='POST'){window.pendingBodies.push(JSON.parse(args[1].body));if(window.dropSavedReply){window.dropSavedReply=false;throw Error('Synthetic saved reply confirmation lost')}}return res}")
  click.call('[data-action=annotation-message]')
  c.wait_for("#{ui}.querySelector('#annotation-panel').textContent.includes('Synthetic saved reply confirmation lost')")
  check.call('Lost save-only response freezes original body and response choice', "#{ui}.querySelector('#annotation-followup').value==='Saved followup context only.'&&#{ui}.querySelector('#annotation-agent-toggle').disabled&&window.pendingBodies[0].autoReply===false")
  frozen_payload = c.evaluate('window.pendingBodies[0]')
  c.call('Page.reload');ready.call;click.call('[data-action=annotations]') unless c.evaluate("!!#{ui}.querySelector('.annotation-sidebar')")
  activate.call(note_id)
  c.evaluate("window.originalBodyStyle=#{original_body_style.to_json}")
  check.call('Refresh preserves pending save-only body and immutable response switch', "#{ui}.querySelector('#annotation-followup').value==='Saved followup context only.'&&#{ui}.querySelector('#annotation-agent-toggle').disabled&&#{ui}.querySelector('#annotation-agent-toggle').getAttribute('aria-checked')==='false'")
  c.evaluate("window.pendingBodies=[#{frozen_payload.to_json}];window.realFetch=fetch;window.fetch=async(...args)=>{const res=await window.realFetch(...args);if(String(args[0]).endsWith('/annotations/message')&&args[1]?.method==='POST')window.pendingBodies.push(JSON.parse(args[1].body));return res}")
  click.call('[data-action=annotation-message]')
  c.wait_for("#{get}.then(a=>a.find(x=>x.id===#{note_id.to_json}).conversation.messages.filter(m=>m.text==='Saved followup context only.').length===1)")
  check.call('Save-only confirmation retries identical message identity body and intent', "window.pendingBodies.length===2&&JSON.stringify(window.pendingBodies[0])===JSON.stringify(window.pendingBodies[1])")
  raise 'Agent-off messages dispatched a turn' unless rpc.call('turn/start') == before
  c.wait_for("!#{ui}.querySelector('#annotation-agent-toggle').disabled&&#{ui}.querySelector('#annotation-followup').value===''")
  click.call('#annotation-agent-toggle') if c.evaluate("#{ui}.querySelector('#annotation-agent-toggle').getAttribute('aria-checked')==='false'")
  sleep 2.2
  raise 'Reenabling Agent backfilled saved messages' unless rpc.call('turn/start') == before
  check.call('Reenabling response control does not auto-dispatch saved history', "#{ui}.querySelector('#annotation-agent-toggle').getAttribute('aria-checked')==='true'")
  fill.call('#annotation-followup', 'Respond only to this explicit current request.')
  click.call('[data-action=annotation-message]')
  c.wait_for("#{get}.then(a=>a.find(x=>x.id===#{note_id.to_json}).conversation?.status==='completed')",30)
  raise 'First Agent followup failed exactly-one turn' unless rpc.call('turn/start') == before+1
  invocation = JSON.parse(File.read(File.join(fixture, 'invocation.json')))
  raise 'First Agent turn lost saved context' unless invocation['prompt'].include?('Saved followup context only.') && invocation['prompt'].include?('Respond only to this explicit current request.')
  check.call('First explicit Agent followup includes saved context once without replaying requests', "#{get}.then(a=>a.find(x=>x.id===#{note_id.to_json}).conversation.messages.some(m=>m.status==='saved'&&m.autoReply===false))")
  c.wait_for("#{ui}.querySelector('#annotation-thread').textContent.includes('临时任务完成')")
  check.call('Root note and final reply each appear once in active card', "(()=>{const card=#{ui}.querySelector('.annotation-card[data-id=\"#{note_id}\"]');return card.querySelectorAll('.from-agent').length===1&&[...card.querySelectorAll('.annotation-text,.from-user p')].filter(p=>p.textContent==='Initial saved note without Agent.').length===1&&[...card.querySelectorAll('.from-agent p')].filter(p=>p.textContent==='临时任务完成，正式评论未修改。').length===1})()")
  2.times do |index|
    c.wait_for("!#{ui}.querySelector('#annotation-agent-toggle').disabled")
    click.call('#annotation-agent-toggle') if c.evaluate("#{ui}.querySelector('#annotation-agent-toggle').getAttribute('aria-checked')==='true'")
    fill.call('#annotation-followup','Legitimate repeated saved reply.')
    click.call('[data-action=annotation-message]')
    c.wait_for("[...#{ui}.querySelectorAll('#annotation-thread .from-user p')].filter(p=>p.textContent==='Legitimate repeated saved reply.').length===#{index+1}&&#{ui}.querySelector('#annotation-followup').value===''")
  end
  check.call('Legitimate equal-text followups retain distinct message identities', "#{get}.then(a=>{const m=a.find(x=>x.id===#{note_id.to_json}).conversation.messages.filter(m=>m.text==='Legitimate repeated saved reply.');return m.length===2&&m[0].id!==m[1].id})")
  raise 'Repeated save-only notes launched Agent' unless rpc.call('turn/start') == before+1
  # Drawer uses same thread, keeps controls available, and returns to its quote.
  c.call('Emulation.setDeviceMetricsOverride',width:390,height:844,deviceScaleFactor:1,mobile:false)
  c.wait_for("!!#{ui}.querySelector('.annotation-sidebar[data-layout=drawer]')")
  check.call('Narrow drawer retains current composer and stays in viewport', "(()=>{const r=#{ui}.querySelector('.annotation-sidebar').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight&&!!#{ui}.querySelector('#annotation-followup')})()")
  b.screenshot(File.join(out, 'narrow-drawer.png'))
  click.call('[data-action=annotation-return]')
  check.call('Return-to-text closes narrow drawer and restores normal body style', "!#{ui}.querySelector('#annotation-followup')&&document.body.getAttribute('style')===window.originalBodyStyle")
  c.call('Emulation.setTouchEmulationEnabled',enabled:true,maxTouchPoints:1)
  c.evaluate("document.querySelector('#first').scrollIntoView({block:'center'});getSelection().removeAllRanges()")
  tap = c.evaluate("(()=>{const n=document.querySelector('#first').firstChild,r=document.createRange();r.setStart(n,2);r.setEnd(n,12);const b=r.getBoundingClientRect();return{x:b.left+b.width/2,y:b.top+b.height/2}})()")
  c.call('Input.dispatchTouchEvent',type:'touchStart',touchPoints:[{x:tap['x'],y:tap['y'],id:1}])
  c.call('Input.dispatchTouchEvent',type:'touchEnd',touchPoints:[])
  c.wait_for("!!#{ui}.querySelector('.annotation-card[data-id=annotation-first] #annotation-followup')")
  check.call('Touch tap on annotated original activates its card in narrow drawer', "!!#{ui}.querySelector('.annotation-sidebar[data-layout=drawer] .annotation-card[data-id=annotation-first].active')")
  tap = c.evaluate("(()=>{const r=#{ui}.querySelector('[data-action=annotation-return]').getBoundingClientRect();return{x:r.left+r.width/2,y:r.top+r.height/2}})()")
  c.call('Input.dispatchTouchEvent',type:'touchStart',touchPoints:[{x:tap['x'],y:tap['y'],id:1}])
  c.call('Input.dispatchTouchEvent',type:'touchEnd',touchPoints:[])
  c.wait_for("!#{ui}.querySelector('#annotation-followup')")
  check.call('Touch return-to-original closes drawer and leaves reading available', "!#{ui}.querySelector('.annotation-sidebar')&&!document.documentElement.hasAttribute('data-prototype-review-active')")
  c.call('Emulation.setTouchEmulationEnabled',enabled:false)
  raise 'Legacy review was mutated by annotation actions' unless File.binread(File.join(fixture,'data/comments.json'))==legacy_bytes
  checks << 'Legacy comments remain separate from all sidebar actions'
  # Disabled, shared and offline entries allow save-only replies; no hidden jobs.
  c.call('Emulation.setDeviceMetricsOverride',width:1440,height:1000,deviceScaleFactor:1,mobile:false)
  c.call('Page.navigate',url:base);ready.call
  c.evaluate("document.body.style.backgroundColor='#181c22';document.body.style.color='#edf0f4'")
  c.evaluate("#{ui}.querySelector('[data-action=annotations]').click()") unless c.evaluate("!!#{ui}.querySelector('.annotation-sidebar')");activate.call('annotation-first')
  check.call('Dark reading document selects dark sidebar with legible message and quote contrast', <<~JS)
    (()=>{const panel=#{ui}.querySelector('#annotation-panel'),card=panel.querySelector('.annotation-card'),style=getComputedStyle(card),quote=card.querySelector('.annotation-quote');
    const luminance=rgb=>rgb.match(/[0-9.]+/g).slice(0,3).map(x=>{const n=Number(x)/255;return n<=.04045?n/12.92:((n+.055)/1.055)**2.4}).reduce((sum,n,i)=>sum+n*[.2126,.7152,.0722][i],0);
    const background=luminance(style.backgroundColor),ratio=color=>{const text=luminance(color);return(Math.max(text,background)+.05)/(Math.min(text,background)+.05)};
    return panel.dataset.theme==='dark'&&ratio(style.color)>=4.5&&ratio(getComputedStyle(quote).color)>=4.5})()
  JS
  b.screenshot(File.join(out,'dark-sidebar.png'))
  # A polling arrival may precede already-mounted cards in document order.
  # Keep an active composing field alive while inserting that earlier record,
  # then verify the same order (including an unsent middle draft) in the drawer.
  seed_order_record = lambda do |name, selector|
    c.evaluate(<<~JS)
      (async()=>{const el=document.querySelector(#{selector.to_json}),text=el.textContent,start=0,end=18,exact=text.slice(start,end);
      const annotation={id:'annotation-order-'+#{name.to_json},text:'Synthetic arrival '+#{name.to_json},status:'open',page:{path:'/',title:'Synthetic reading'},attachments:[],
      screenshotData:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLttAAAAABJRU5ErkJggg==',
      anchor:{kind:'text',selector:#{selector.to_json},selectedText:exact,textRange:{start,end,exact,prefix:'',suffix:text.slice(end,end+40)}}};
      const response=await fetch('/__review/annotations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({annotation,autoReply:false})});if(!response.ok)throw Error(await response.text());})()
    JS
  end
  seed_order_record.call('late','#last')
  c.wait_for("!!#{ui}.querySelector('.annotation-card[data-id=annotation-order-late]')")
  activate.call('annotation-order-late')
  fill.call('#annotation-followup','Keep focused IME draft while an earlier record arrives.')
  c.evaluate("window.orderField=#{ui}.querySelector('#annotation-followup');window.orderCard=window.orderField.closest('.annotation-card');window.orderField.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}))")
  seed_order_record.call('early','#first')
  c.wait_for("!!#{ui}.querySelector('.annotation-card[data-id=annotation-order-early]')")
  c.evaluate("window.orderFocusRetained=#{ui}.querySelector('#annotation-followup')===window.orderField&&#{ui}.activeElement===window.orderField&&window.orderField.closest('.annotation-card')===window.orderCard&&window.orderField.value==='Keep focused IME draft while an earlier record arrives.';window.orderField.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true}));scrollTo(0,0)")
  c.evaluate("(()=>{const n=document.querySelector('#adjacent').firstChild,r=document.createRange();r.setStart(n,0);r.setEnd(n,12);getSelection().removeAllRanges();getSelection().addRange(r);document.dispatchEvent(new Event('selectionchange'))})()")
  c.wait_for("!!#{ui}.querySelector('[data-action=annotation-create]')")
  click.call('[data-action=annotation-create]')
  c.wait_for("!!#{ui}.querySelector('#annotation-input')")
  fill.call('#annotation-input','Unsent draft follows its original text order.')
  c.evaluate("window.orderedDraft=#{ui}.querySelector('#annotation-input');window.orderedDraftCard=window.orderedDraft.closest('.annotation-card');window.orderedDraft.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}))")
  c.call('Emulation.setDeviceMetricsOverride',width:390,height:844,deviceScaleFactor:1,mobile:false)
  c.wait_for("!!#{ui}.querySelector('.annotation-sidebar[data-layout=drawer]')")
  sleep 2.0
  check.call('Earlier polling arrival and unsent draft follow document order in drawer without replacing focused IME fields', <<~JS)
    (()=>{const cards=[...#{ui}.querySelectorAll('.annotation-card')],early=cards.findIndex(e=>e.dataset.id==='annotation-order-early'),draft=cards.indexOf(window.orderedDraftCard),late=cards.findIndex(e=>e.dataset.id==='annotation-order-late');
    return window.orderFocusRetained&&early>=0&&early<draft&&draft<late&&cards[early].getBoundingClientRect().top<cards[draft].getBoundingClientRect().top&&cards[draft].getBoundingClientRect().top<cards[late].getBoundingClientRect().top&&#{ui}.querySelector('#annotation-input')===window.orderedDraft&&#{ui}.activeElement===window.orderedDraft&&window.orderedDraft.value==='Unsent draft follows its original text order.'})()
  JS
  c.evaluate("window.orderedDraft.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true}))")
  c.evaluate("#{ui}.querySelector('[data-action=annotation-discard]').click()")
  c.call('Emulation.setDeviceMetricsOverride',width:1440,height:1000,deviceScaleFactor:1,mobile:false)
  ['ANNOTATIONS_SHARED_URL','ANNOTATIONS_OFFLINE_URL'].each do |environment|
    c.call('Page.navigate',url:ENV.fetch(environment));ready.call
    c.evaluate("(()=>{const n=document.querySelector('#first').firstChild,r=document.createRange();r.setStart(n,0);r.setEnd(n,20);getSelection().removeAllRanges();getSelection().addRange(r);document.dispatchEvent(new Event('selectionchange'));document.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}))})()")
    c.wait_for("!!#{ui}.querySelector('[data-action=annotation-create]')")
    click.call('[data-action=annotation-create]')
    check.call("#{environment} makes unavailable Agent switch disabled/effectively off", "#{ui}.querySelector('#annotation-agent-toggle').disabled&&#{ui}.querySelector('#annotation-agent-toggle').getAttribute('aria-checked')==='false'")
    fill.call('#annotation-input',"Synthetic root #{environment}");click.call('[data-action=annotation-send]')
    c.wait_for("!!#{ui}.querySelector('#annotation-followup')",30)
    fill.call('#annotation-followup',"Synthetic saved reply #{environment}");click.call('[data-action=annotation-message]')
    c.wait_for("#{ui}.querySelector('#annotation-thread').textContent.includes('Synthetic saved reply #{environment}')")
    c.call('Page.reload');ready.call;click.call('[data-action=annotations]') unless c.evaluate("!!#{ui}.querySelector('.annotation-sidebar')")
    c.wait_for("#{ui}.querySelector('#annotation-panel').textContent.includes('Synthetic root #{environment}')")
    check.call("#{environment} saves and reloads followups without Agent", "#{ui}.querySelector('#annotation-panel').textContent.includes('Synthetic saved reply #{environment}')")
  end
  raise 'Shared/offline checks dispatched Agent' unless rpc.call('turn/start') == before+1
  %w[failure.png failure-state.json failure.txt].each { |name| FileUtils.rm_f(File.join(out,name)) }
  errors = c.events.select { |event| event['method']=='Runtime.exceptionThrown' }
  raise errors.to_json unless errors.empty?
  File.write(File.join(out,'results.json'),JSON.pretty_generate(checks:checks,protocolFixtureOnly:true,runtimeErrors:errors,nativeScroll:{text:moved_text,card:moved_card}))
  puts "#{checks.length} sidebar browser checks passed; protocol fixture only."
rescue => error
  b.screenshot(File.join(out,'failure.png')) rescue nil
  File.write(File.join(out,'failure-state.json'),JSON.pretty_generate(c.evaluate("({url:location.href,scrollY,selection:getSelection()?.toString(),body:document.body.getAttribute('style'),ui:#{ui}.innerHTML})"))) rescue nil
  File.write(File.join(out,'failure.txt'),error.full_message)
  raise
ensure
  b.close
end
