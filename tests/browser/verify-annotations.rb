require_relative '../support/browser'

# Launched by test_annotations_browser.py against temporary synthetic services only.
root = File.expand_path('../..', __dir__)
out = File.join(root, 'artifacts/validation-annotations')
FileUtils.mkdir_p(out)
base = ENV.fetch('ANNOTATIONS_TEST_URL')
fixture = ENV.fetch('ANNOTATIONS_FIXTURE')
ui = "document.querySelector('#prototype-review').shadowRoot"
b = PrototypeBrowser.new
c = b.cdp
checks = []
check = lambda { |name, expression| raise name unless c.evaluate(expression); checks << name; puts "PASS #{name}" }
click = lambda do |selector|
  xy = c.evaluate("(async()=>{const e=#{ui}.querySelector(#{selector.to_json});if(!e)throw Error('Missing control '+#{selector.to_json});e.scrollIntoView({block:'nearest'});let r=e.getBoundingClientRect();if(#{ui}.querySelector('.annotation-sidebar')?.dataset.layout==='aligned'&&r.bottom>innerHeight-20){scrollBy(0,r.bottom-innerHeight+80);await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);r=e.getBoundingClientRect()}return{x:r.x+r.width/2,y:r.y+r.height/2}})()")
  c.call('Input.dispatchMouseEvent', type: 'mousePressed', x: xy['x'], y: xy['y'], button: 'left', clickCount: 1)
  c.call('Input.dispatchMouseEvent', type: 'mouseReleased', x: xy['x'], y: xy['y'], button: 'left', clickCount: 1)
end
key = lambda do |name, modifiers = 0|
  code = {'Escape'=>27, 'Enter'=>13, 'Tab'=>9}.fetch(name)
  c.call('Input.dispatchKeyEvent', type:'keyDown', key:name, code:name, modifiers:modifiers,
         windowsVirtualKeyCode:code, text:name == 'Enter' && modifiers == 0 ? "\r" : '')
  c.call('Input.dispatchKeyEvent', type:'keyUp', key:name, code:name, windowsVirtualKeyCode:code)
end
ready = lambda do
  c.wait_for("!!window.PrototypeReview&&!!#{ui}.querySelector('[data-action=annotations]')")
  c.wait_for("(()=>{const style=getComputedStyle(#{ui}.querySelector('#toolbar'));return style.visibility==='visible'&&style.position==='fixed';})()")
end
select = lambda do |selector, start, finish, reverse = false|
  c.evaluate(<<~JS)
    (()=>{const el=document.querySelector(#{selector.to_json}),walk=document.createTreeWalker(el,NodeFilter.SHOW_TEXT),nodes=[];let n;
    while(n=walk.nextNode())nodes.push(n);function at(offset){for(const n of nodes){if(offset<=n.length)return[n,offset];offset-=n.length}throw Error('Selection offset');}
    const a=at(#{start}),z=at(#{finish}),selection=getSelection();selection.removeAllRanges();
    selection.setBaseAndExtent(...#{reverse ? 'z' : 'a'},...#{reverse ? 'a' : 'z'});
    document.dispatchEvent(new Event('selectionchange'));document.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));return selection.toString()})()
  JS
end
open_composer = lambda do |selector = '#cross', start = 7, finish = 21, reverse = false|
  quote = select.call(selector, start, finish, reverse)
  c.wait_for("!!#{ui}.querySelector('[data-action=annotation-create]')&&#{ui}.querySelector('#annotation-selection').getBoundingClientRect().width>0")
  click.call('[data-action=annotation-create]')
  c.wait_for("!!#{ui}.querySelector('#annotation-input')")
  quote
end
fill = lambda do |selector, text|
  c.evaluate("(()=>{const e=#{ui}.querySelector(#{selector.to_json});e.focus();e.select()})()")
  c.call('Input.insertText', text:text)
end
get_annotations = "fetch('/__review/annotations').then(r=>r.json()).then(d=>d.annotations)"
status = lambda do |id, value|
  c.wait_for("#{get_annotations}.then(a=>a.find(a=>a.id===#{id.to_json})?.conversation?.status===#{value.to_json})", 25)
end
rpc = lambda do |method|
  path = File.join(fixture, 'rpc.jsonl')
  File.exist?(path) ? File.readlines(path).map { |line| JSON.parse(line) }.count { |request| request['method'] == method } : 0
end
begin
  $stdout.sync = true
  c.call('Emulation.setDeviceMetricsOverride', width:1440, height:1000, deviceScaleFactor:1, mobile:false)
  c.call('Page.navigate', url:base)
  c.call('Page.bringToFront')
  ready.call
  check.call('Normal reading keeps review mode inactive', "!document.documentElement.hasAttribute('data-prototype-review-active')")
  points = c.evaluate(<<~JS)
    (()=>{const text=document.querySelector('#reverse').firstChild,start=document.createRange(),end=document.createRange();
    start.setStart(text,0);start.setEnd(text,1);end.setStart(text,16);end.setEnd(text,17);
    const a=start.getBoundingClientRect(),z=end.getBoundingClientRect();return{ax:a.left+1,ay:a.top+a.height/2,zx:z.right-1,zy:z.top+z.height/2}})()
  JS
  c.call('Input.dispatchMouseEvent', type:'mouseMoved', x:points['ax'], y:points['ay'])
  c.call('Input.dispatchMouseEvent', type:'mousePressed', x:points['ax'], y:points['ay'], button:'left', buttons:1, clickCount:1)
  12.times do |index|
    fraction = (index + 1) / 12.0
    c.call('Input.dispatchMouseEvent', type:'mouseMoved', x:points['ax']+(points['zx']-points['ax'])*fraction,
           y:points['ay']+(points['zy']-points['ay'])*fraction, button:'left', buttons:1)
  end
  c.call('Input.dispatchMouseEvent', type:'mouseReleased', x:points['zx'], y:points['zy'], button:'left', clickCount:1)
  c.wait_for("!!#{ui}.querySelector('[data-action=annotation-create]')&&#{ui}.querySelector('#annotation-selection').getBoundingClientRect().width>0")
  check.call('Native mouse selection offers an annotation without entering review mode', "getSelection().toString().includes('Reverse selection')&&!document.documentElement.hasAttribute('data-prototype-review-active')")
  c.evaluate("getSelection().removeAllRanges();document.dispatchEvent(new Event('selectionchange'))")
  c.wait_for("!#{ui}.querySelector('[data-action=annotation-create]')||#{ui}.querySelector('#annotation-selection').getBoundingClientRect().width===0")
  check.call('Collapsed selection dismisses the reading action', 'getSelection().isCollapsed')
  quote = open_composer.call
  check.call('Cross-inline selection preserves quote and focuses composer', "#{ui}.querySelector('#annotation-panel').textContent.includes(#{quote.to_json})&&#{ui}.activeElement===#{ui}.querySelector('#annotation-input')")
  key.call('Escape')
  check.call('Escape cancels an unsent annotation', "!#{ui}.querySelector('#annotation-input')")
  quote = open_composer.call('#reverse', 0, 17, true)
  check.call('Reverse selection preserves reading order', "#{ui}.querySelector('#annotation-panel').textContent.includes(#{quote.to_json})")
  key.call('Escape')
  quote = open_composer.call('#multiline', 0, 57)
  check.call('Multiline selection preserves complete quote', "#{ui}.querySelector('#annotation-panel').textContent.includes(#{quote.to_json})")
  key.call('Escape')
  c.evaluate("const input=document.querySelector('#ordinary-input');input.focus();input.select();document.dispatchEvent(new Event('selectionchange'))")
  check.call('Editable input does not offer an annotation action', "!#{ui}.querySelector('[data-action=annotation-create]')||#{ui}.querySelector('#annotation-selection').getBoundingClientRect().width===0")
  c.evaluate('getSelection().removeAllRanges();document.activeElement.blur()')
  click.call('[data-action=toggle]')
  select.call('#cross', 7, 21)
  check.call('Existing review mode suppresses natural annotation entry', "!#{ui}.querySelector('[data-action=annotation-create]')||#{ui}.querySelector('#annotation-selection').getBoundingClientRect().width===0")
  key.call('Escape') if c.evaluate("!!#{ui}.querySelector('#note-input')")
  click.call('[data-action=toggle]')
  open_composer.call
  fill.call('#annotation-input', 'Explain this synthetic selection.')
  c.evaluate("#{ui}.querySelector('#annotation-input').dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));#{ui}.querySelector('#annotation-input').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',ctrlKey:true,isComposing:true,bubbles:true}))")
  check.call('IME confirmation does not submit the annotation', "#{get_annotations}.then(a=>a.length===0)")
  c.evaluate("#{ui}.querySelector('#annotation-input').dispatchEvent(new CompositionEvent('compositionend',{bubbles:true}))")
  c.evaluate(<<~JS)
    (()=>{const canvas=document.createElement('canvas');canvas.width=8;canvas.height=8;canvas.getContext('2d').fillRect(0,0,8,8);
    const bytes=Uint8Array.from(atob(canvas.toDataURL().split(',')[1]),x=>x.charCodeAt(0)),data=new DataTransfer();
    data.items.add(new File([bytes],'synthetic-annotation.png',{type:'image/png'}));
    #{ui}.querySelector('#annotation-input').dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,composed:true,cancelable:true}));})()
  JS
  c.wait_for("#{ui}.querySelector('#annotation-panel img')?.naturalWidth===8")
  # Hold only this temporary project's execution lock to expose the persisted queue.
  lock = File.open(File.join(fixture, 'jobs/active.lock'), 'a+')
  lock.flock(File::LOCK_EX)
  c.evaluate("window.initialAnnotationFetch=window.fetch;window.dropInitialAnnotation=true;window.fetch=async(...args)=>{const r=await window.initialAnnotationFetch(...args);if(String(args[0]).endsWith('/annotations')&&args[1]?.method==='POST'&&window.dropInitialAnnotation){window.dropInitialAnnotation=false;window.initialAnnotationPayload=JSON.parse(args[1].body);throw Error('Synthetic lost initial response')}return r}")
  click.call('[data-action=annotation-send]')
  c.wait_for("#{get_annotations}.then(a=>a.length===1)", 30)
  c.wait_for("#{ui}.querySelector('#annotation-error').textContent.includes('Synthetic lost initial response')")
  check.call('Lost initial response retains original quote and immutable pending submission', "#{ui}.querySelector('#annotation-input').value==='Explain this synthetic selection.'&&#{ui}.querySelector('#annotation-input').disabled")
  # Simulate a verified fixture worker updating the saved record before its lost
  # initial response can be confirmed. Retry must retain this fresher status.
  c.evaluate(<<~JS)
    (async()=>{const current=(await(await fetch('/__review/annotations')).json()).annotations[0];
    const response=await fetch('/__review/annotations',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({annotation:{...current,status:'changed',resolution:'Synthetic verified change before confirmation'},expectedUpdate:current.updatedAt})});
    if(!response.ok)throw Error('Synthetic concurrent status update failed');window.changedBeforeConfirmation=(await response.json()).annotation;})()
  JS
  click.call('[data-action=annotation-send]')
  c.wait_for("!!#{ui}.querySelector('#annotation-followup')", 30)
  check.call('Duplicate initial submit confirms the same annotation once', "#{get_annotations}.then(a=>a.length===1&&a[0].id===window.initialAnnotationPayload.annotation.id)")
  check.call('Retry confirms fresh changed record and clears pending draft without overwriting status', "#{get_annotations}.then(a=>a[0].status==='changed'&&a[0].updatedAt===window.changedBeforeConfirmation.updatedAt&&a[0].resolution==='Synthetic verified change before confirmation'&&!#{ui}.querySelector('#annotation-input'))")
  first = c.evaluate("#{get_annotations}.then(a=>a[0])")
  first_id = first.fetch('id')
  status.call(first_id, 'queued')
  check.call('Saved annotation reports waiting while another execution holds the lock', "#{ui}.querySelector('#annotation-state').textContent.includes('等待 Agent')")
  lock.flock(File::LOCK_UN)
  lock.close
  lock = nil
  status.call(first_id, 'running')
  raise 'Initial response confirmation duplicated execution' unless rpc.call('turn/start') == 1
  c.wait_for("#{ui}.querySelector('#annotation-state').textContent.includes('Agent 回复中')")
  check.call('Annotations and legacy review counts remain separate', "#{ui}.querySelector('.count').textContent==='1'&&fetch('/__review/comments').then(r=>r.json()).then(d=>d.comments.length===1)")
  check.call('Initial screenshot, image attachment and exact text offsets persist', "#{get_annotations}.then(a=>{const x=a[0];return x.screenshot&&x.attachments.length===1&&x.anchor.textRange.exact==='reading across'&&x.anchor.textRange.end>x.anchor.textRange.start})")
  check.call('Saved screenshot and attached image are readable evidence', "#{get_annotations}.then(async a=>{const x=a[0];return(await fetch(x.screenshot)).ok&&(await fetch(x.attachments[0].url)).ok})")
  fill.call('#annotation-followup', 'Unsent draft survives progress polling.')
  c.evaluate("window.annotationField=#{ui}.querySelector('#annotation-followup')")
  sleep 2.2
  check.call('Progress polling preserves draft, textarea identity and focus', "#{ui}.querySelector('#annotation-followup')===window.annotationField&&#{ui}.activeElement===window.annotationField&&window.annotationField.value==='Unsent draft survives progress polling.'")
  before = rpc.call('turn/start')
  c.call('Page.reload')
  ready.call
  click.call('[data-action=annotations]') unless c.evaluate("#{ui}.querySelector('[data-action=annotations]').getAttribute('aria-expanded')==='true'")
  c.wait_for("!!#{ui}.querySelector('.annotation-card [data-action=annotation-open][data-id=\"#{first_id}\"]')")
  click.call(".annotation-card [data-action=annotation-open][data-id='#{first_id}']")
  c.wait_for("!!#{ui}.querySelector('#annotation-followup')")
  check.call('Refresh restores conversation and unsent draft', "#{ui}.querySelector('#annotation-followup').value==='Unsent draft survives progress polling.'&&#{ui}.querySelector('.annotation-card:has(#annotation-followup)').textContent.includes('Explain this synthetic selection.')")
  raise 'Refresh dispatched a second turn' unless rpc.call('turn/start') == before
  click.call('[data-action=annotation-stop]')
  status.call(first_id, 'cancelled')
  c.wait_for("#{ui}.querySelector('#annotation-state').textContent.includes('已停止')")
  File.write(File.join(fixture, 'behavior'), 'fail')
  click.call('[data-action=annotation-retry]')
  status.call(first_id, 'failed')
  c.wait_for("#{ui}.querySelector('#annotation-state').textContent.includes('未完成')")
  check.call('Failed execution remains explicit and retryable', "!!#{ui}.querySelector('[data-action=annotation-retry]')")
  File.write(File.join(fixture, 'behavior'), 'ok')
  click.call('[data-action=annotation-retry]')
  status.call(first_id, 'completed')
  c.wait_for("#{ui}.querySelector('#annotation-thread').textContent.includes('临时任务完成')")
  check.call('Question completion preserves the latest review state without accepting it', "#{get_annotations}.then(a=>a[0].status==='changed')")
  fill.call('#annotation-followup', 'Continue explaining this annotation.')
  before = rpc.call('turn/start')
  c.evaluate("window.originalAnnotationFetch=window.fetch;window.dropAnnotationReply=true;window.fetch=async(...args)=>{const r=await window.originalAnnotationFetch(...args);if(String(args[0]).endsWith('/annotations/message')&&window.dropAnnotationReply){window.dropAnnotationReply=false;throw Error('Synthetic lost annotation response')}return r}")
  click.call('[data-action=annotation-message]')
  c.wait_for("#{ui}.querySelector('#annotation-panel').textContent.includes('Synthetic lost annotation response')")
  check.call('Lost followup response preserves the message draft', "#{ui}.querySelector('#annotation-followup').value==='Continue explaining this annotation.'")
  click.call('[data-action=annotation-message]')
  c.wait_for("#{get_annotations}.then(a=>a[0].conversation.messages.filter(m=>m.role==='user'&&m.text==='Continue explaining this annotation.').length===1)")
  status.call(first_id, 'completed')
  raise 'Retry duplicated an execution' unless rpc.call('turn/start') == before + 1
  raise 'Historical followup did not resume original thread' unless rpc.call('thread/resume') > 0
  check.call('Historical followup resumes its original conversation exactly once', "#{get_annotations}.then(a=>a.length===1&&a[0].conversation.messages.some(m=>m.role==='agent'||m.role==='assistant'))")
  c.call('Emulation.setDeviceMetricsOverride', width:390, height:844, deviceScaleFactor:1, mobile:false)
  c.wait_for("(()=>{const r=#{ui}.querySelector('#annotation-panel').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight})()")
  check.call('Narrow screen keeps the composer send control visible', "(()=>{const r=#{ui}.querySelector('[data-action=annotation-message]').getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight})()")
  b.screenshot(File.join(out, 'narrow-conversation.png'))
  key.call('Escape')
  check.call('Escape closes the annotation panel and leaves natural reading active', "!#{ui}.querySelector('#annotation-followup')&&!document.documentElement.hasAttribute('data-prototype-review-active')")
  check.call('Closing the panel returns keyboard focus to its separate entry', "#{ui}.activeElement?.dataset.action==='annotations'")
  key.call('Enter')
  c.wait_for("!!#{ui}.querySelector('.annotation-card')")
  check.call('Keyboard activation reopens the independent annotation sidebar', "#{ui}.querySelector('[data-action=annotations]').getAttribute('aria-expanded')==='true'")
  key.call('Escape')
  c.call('Emulation.setDeviceMetricsOverride', width:1440, height:1000, deviceScaleFactor:1, mobile:false)
  before = rpc.call('turn/start')
  # Shared and disabled services persist annotations but never execute or queue them.
  ['ANNOTATIONS_SHARED_URL', 'ANNOTATIONS_DISABLED_URL'].each do |environment|
    if environment == 'ANNOTATIONS_SHARED_URL'
      # Seed an independent synthetic reader; never share a live writer directory.
      %w[annotations.json screenshots attachments annotation-threads].each do |name|
        source = File.join(fixture, 'data', name)
        FileUtils.cp_r(source, File.join(fixture, 'shared-data', name)) if File.exist?(source)
      end
    end
    c.call('Page.navigate', url:ENV.fetch(environment))
    ready.call
    open_composer.call
    message_text = "No automatic Agent in #{environment}"
    message_text += ' </script><script>window.annotationExportInjected=true</script>' if environment == 'ANNOTATIONS_SHARED_URL'
    fill.call('#annotation-input', message_text)
    click.call('[data-action=annotation-send]')
    path = environment == 'ANNOTATIONS_SHARED_URL' ? '/team/review/__review/annotations' : '/__review/annotations'
    c.wait_for("fetch(#{path.to_json}).then(r=>r.json()).then(d=>d.annotations.some(a=>a.text===#{message_text.to_json}))", 30)
    check.call("#{environment} saves without automatic Agent", "fetch(#{path.to_json}).then(r=>r.json()).then(d=>!d.agent.enabled&&d.annotations.filter(a=>a.text===#{message_text.to_json}).every(a=>!a.conversation||!['queued','starting','running'].includes(a.conversation.status)))")
    if environment == 'ANNOTATIONS_SHARED_URL'
      check.call('Shared reader retains public historical Agent replies', "fetch(#{path.to_json}).then(r=>r.json()).then(d=>d.annotations.find(a=>a.id===#{first_id.to_json}).conversation.result.includes('临时任务完成'))")
      downloads = File.join(fixture, 'downloads')
      FileUtils.mkdir_p(downloads)
      c.call('Page.setDownloadBehavior', behavior:'allow', downloadPath:downloads)
      c.evaluate("#{ui}.querySelector('.annotation-sidebar > header details').open=true")
      click.call('[data-action=annotation-export]')
      exported = nil
      Timeout.timeout(20) do
        loop do
          exported = Dir[File.join(downloads, '*.html')].first
          break if exported
          sleep 0.1
        end
      end
      html = File.read(exported)
      payload = JSON.parse(html.match(/<script type="application\/json" id="annotation-export-data">(.*?)<\/script>/m)[1])
      historical = payload.fetch('annotations').find { |record| record['id'] == first_id }
      raise 'Export omitted embedded screenshot or image' unless historical['screenshotData'].start_with?('data:image/png;base64,') && historical['attachments'][0]['dataUrl'].start_with?('data:image/png;base64,')
      raise 'Export exposed fixture project path' if html.include?(fixture)
      raise 'Export altered malicious text instead of preserving it as inert data' unless payload.fetch('annotations').any? { |record| record['text'] == message_text }
      checks << 'Export embeds public replies and original screenshot/image without private paths'
      c.call('Page.navigate', url:'file://' + exported)
      c.wait_for("document.body.textContent.includes('临时任务完成')&&document.images[0]?.naturalWidth>0")
      check.call('Exported annotation artifact is readable without the service', "!window.PrototypeReview&&document.body.textContent.includes('Explain this synthetic selection.')")
      check.call('Exported script-closing text remains inert and round-trips exactly', "window.annotationExportInjected!==true&&document.querySelectorAll('script:not([type=\"application/json\"])').length===0&&JSON.parse(document.querySelector('#annotation-export-data').textContent).annotations.some(a=>a.text===#{message_text.to_json})")
    else
      key.call('Escape')
      open_composer.call('#stale', 2, 23)
      fill.call('#annotation-input', 'Original quote must never relocate to unrelated text.')
      click.call('[data-action=annotation-send]')
      c.wait_for("!!#{ui}.querySelector('#annotation-followup')", 30)
      c.evaluate("document.querySelector('#stale').textContent='The original wording is entirely gone.';window.dispatchEvent(new Event('resize'))")
      click.call('#annotation-quote')
      c.wait_for("#{ui}.querySelector('#notice').textContent.includes('原文位置已变化')")
      check.call('Changed original text keeps its saved quote and reports location drift', "#{ui}.querySelector('#annotation-quote').textContent.includes('unique original quote')")
      key.call('Escape')
      open_composer.call('#duplicate', 0, 15)
      fill.call('#annotation-input', 'Ambiguous duplicate text cannot be guessed.')
      click.call('[data-action=annotation-send]')
      c.wait_for("!!#{ui}.querySelector('#annotation-followup')", 30)
      c.evaluate("document.querySelector('#duplicate').textContent='Changed prefix Repeated quote. Changed middle Repeated quote.';window.dispatchEvent(new Event('resize'))")
      click.call('#annotation-quote')
      c.wait_for("#{ui}.querySelector('#notice').textContent.includes('原文位置已变化')")
      check.call('Ambiguous repeated quotes do not create an unrelated highlight', "#{ui}.querySelector('#annotation-quote').textContent==='Repeated quote.'")
    end
  end
  raise 'Shared or disabled entry dispatched a task' unless rpc.call('turn/start') == before
  c.call('Page.navigate', url:ENV.fetch('ANNOTATIONS_OFFLINE_URL'))
  ready.call
  open_composer.call
  fill.call('#annotation-input', 'Offline content annotation persists independently.')
  click.call('[data-action=annotation-send]')
  c.wait_for("#{ui}.querySelector('#annotation-panel').textContent.includes('Offline content annotation persists independently.')&&!#{ui}.querySelector('#annotation-input')")
  c.call('Page.reload')
  ready.call
  click.call('[data-action=annotations]') unless c.evaluate("!!#{ui}.querySelector('.annotation-sidebar')")
  c.wait_for("#{ui}.querySelector('#annotation-panel').textContent.includes('Offline content annotation persists independently.')")
  check.call('Offline annotations persist separately from legacy comments', "#{ui}.querySelector('.count').textContent==='0'")
  raise 'Shared/offline entry dispatched a task' unless rpc.call('turn/start') == before
  %w[failure.png failure-state.json failure.txt].each { |name| FileUtils.rm_f(File.join(out,name)) }
  errors = c.events.select { |event| event['method'] == 'Runtime.exceptionThrown' }
  raise errors.to_json unless errors.empty?
  File.write(File.join(out, 'results.json'), JSON.pretty_generate(checks:checks, protocolFixtureOnly:true, runtimeErrors:errors))
  puts "#{checks.length} annotation browser checks passed; protocol fixture only."
rescue => error
  b.screenshot(File.join(out, 'failure.png')) rescue nil
  File.write(File.join(out, 'failure-state.json'), JSON.pretty_generate(c.evaluate("({selection:getSelection()?.toString(),active:document.activeElement?.outerHTML,review:#{ui}.innerHTML})"))) rescue nil
  File.write(File.join(out, 'failure.txt'), error.full_message)
  raise
ensure
  lock.close if defined?(lock) && lock && !lock.closed?
  b.close
end
