require_relative '../support/browser'

# All files and services below are owned by run_browser_check's temporary fixture.
# These snapshots never dispatch Codex, including the protocol substitute.
root=File.expand_path('../..',__dir__)
out=File.join(root,'artifacts/validation-annotation-refresh')
FileUtils.mkdir_p(out)
fixture=ENV.fetch('ANNOTATIONS_FIXTURE')
base=ENV.fetch('ANNOTATIONS_TEST_URL')
ui="document.querySelector('#prototype-review').shadowRoot"
legacy=File.binread(File.join(fixture,'data/comments.json'))
b=PrototypeBrowser.new
c=b.cdp
checks=[]
check=lambda{|name,expression|raise name unless c.evaluate(expression);checks<<name;puts "PASS #{name}"}
ready=lambda{c.wait_for("window.PrototypeReview&&#{ui}.querySelector('link').sheet&&#{ui}.querySelector('[data-action=annotations]')")}
click=lambda{|selector|c.evaluate("#{ui}.querySelector(#{selector.to_json}).click()")}
activate=lambda{|id|click.call(".annotation-card[data-id=#{id}] [data-action=annotation-open]");c.wait_for("#{ui}.querySelector('.annotation-card[data-id=#{id}] #annotation-followup')")}
fill=lambda{|text|c.evaluate("#{ui}.querySelector('#annotation-followup').focus();#{ui}.querySelector('#annotation-followup').select()");c.call('Input.insertText',text:text)}
thread_dir=File.join(fixture,'data/annotation-threads')
FileUtils.mkdir_p(thread_dir)
long_text=(1..20).map{|n|"Synthetic answer #{n} retains the conversation across page refresh."}.join("\n")
write_fixture=lambda{|path,value|File.write(path+'.tmp',value);File.rename(path+'.tmp',path)}
thread=lambda do |id,status,text=long_text|
  write_fixture.call(File.join(thread_dir,id+'.json'),JSON.generate(id:id,status:status,hasAgent:true,canChat:true,
    messages:[{id:'synthetic-'+id,role:'assistant',text:text,status:'sent',createdAt:1,turnId:'synthetic-turn'}],result:status=='completed' ? text : ''))
end
sync=lambda{c.evaluate("window.dispatchEvent(new Event('focus'))");sleep 0.25}
same_load=lambda do |name,load|
  3.times{sync.call;sleep 0.35}
  check.call(name,"window.refreshFixtureLoad===#{load}")
end
revision=0
rebuild=lambda do
  revision+=1
  page=File.join(fixture,'pages/index.html')
  html=File.read(page).sub(/<body(?: data-fixture-build="\d+")?>/,"<body data-fixture-build=\"#{revision}\">")
  write_fixture.call(page,html)
  revision
end
mark_changed=lambda do |id='annotation-refresh'|
  c.evaluate(<<~JS)
    (async()=>{const endpoint=new URL('__review/annotations',location.href),data=await fetch(endpoint).then(r=>r.json()),record=data.annotations.find(a=>a.id===#{id.to_json});
    const response=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({annotation:{...record,status:'changed',resolution:'Synthetic checked build #{revision}'},expectedUpdate:record.updatedAt})});if(!response.ok)throw Error(await response.text());return(await response.json()).annotation.updatedAt;})()
  JS
end
start_edit=lambda do
  thread.call('annotation-refresh','running','Synthetic edit is still checking.')
  sync.call
  c.wait_for("#{ui}.querySelector('.annotation-card[data-id=annotation-refresh] [data-part=state]').textContent.includes('回复中')")
  rebuild.call
  mark_changed.call
  sync.call
end
complete_edit=lambda{thread.call('annotation-refresh','completed',"Synthetic verified edit #{revision} is complete.");sync.call}
wait_reload=lambda do |load|
  c.wait_for("window.refreshFixtureLoad===#{load+1}",15);ready.call
  c.wait_for("#{ui}.querySelector('.annotation-card[data-id=annotation-refresh] #annotation-followup')")
  check.call('Completed edit loads its rebuilt HTML and restores the current conversation',"document.body.dataset.fixtureBuild===#{revision.to_s.to_json}&&#{ui}.querySelector('#annotation-thread').textContent.includes('Synthetic verified edit #{revision}')")
end
begin
  $stdout.sync=true
  c.call('Emulation.setDeviceMetricsOverride',width:1440,height:1000,deviceScaleFactor:1,mobile:false)
  c.call('Page.navigate',url:base);ready.call
  c.evaluate(<<~JS)
    (async()=>{for(const [id,selector,status,path] of [['annotation-refresh','#target','changed','/'],['annotation-resolved','#top','resolved','/'],['annotation-other','#other-target','open','/other.html']]){
      const el=document.querySelector(selector),exact=el.textContent;
      const annotation={id,text:'Synthetic note '+id,status,page:{path,title:'Synthetic refresh'},screenshotData:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLttAAAAABJRU5ErkJggg==',anchor:{kind:'text',selector,tag:'P',selectedText:exact,textRange:{start:0,end:exact.length,exact,prefix:'',suffix:''}},attachments:[]};
      const response=await fetch('/__review/annotations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({annotation,autoReply:false})});if(!response.ok)throw Error(await response.text());
    }})()
  JS
  thread.call('annotation-refresh','completed')
  c.call('Page.reload');ready.call
  click.call('[data-action=annotations]')
  c.wait_for("#{ui}.querySelector('.annotation-card[data-id=annotation-refresh]')")
  click.call('[data-action=annotation-filter][data-filter=all]')
  activate.call('annotation-refresh')
  click.call('.annotation-card[data-id=annotation-refresh] [data-action=annotation-expand]')
  c.evaluate('scrollTo(0,620)');sleep 0.2
  before_scroll=c.evaluate('scrollY')
  before_load=c.evaluate('window.refreshFixtureLoad')
  c.call('Page.reload');ready.call
  c.wait_for("#{ui}.querySelector('.annotation-card[data-id=annotation-refresh] #annotation-followup')",5)
  check.call('Manual reload restores open sidebar, current thread, all filter and expanded reply',"#{ui}.querySelector('#annotation-title').textContent.includes('全部')&&#{ui}.querySelectorAll('.annotation-card').length===2&&!#{ui}.querySelector('.annotation-card[data-id=annotation-refresh] .annotation-collapsed')")
  c.wait_for("Math.abs(scrollY-#{before_scroll})<5")
  check.call('Manual reload restores document reading position without a reload loop',"Math.abs(scrollY-#{before_scroll})<5&&window.refreshFixtureLoad===#{before_load+1}")
  same_load.call('Historical completed edits do not reload on startup or repeated polls',before_load+1)

  c.call('Emulation.setDeviceMetricsOverride',width:390,height:844,deviceScaleFactor:1,mobile:false)
  c.wait_for("#{ui}.querySelector('.annotation-sidebar').dataset.layout==='drawer'")
  c.evaluate("#{ui}.querySelector('.annotation-sidebar').scrollTop=260")
  sleep 0.2
  drawer_top=c.evaluate("#{ui}.querySelector('.annotation-sidebar').scrollTop")
  raise 'Fixture drawer must scroll' unless drawer_top>100
  c.call('Page.reload');ready.call
  c.wait_for("#{ui}.querySelector('.annotation-card[data-id=annotation-refresh] #annotation-followup')")
  c.wait_for("Math.abs(#{ui}.querySelector('.annotation-sidebar').scrollTop-#{drawer_top})<5")
  check.call('Manual narrow reload restores current card and drawer scroll position',"#{ui}.querySelector('.annotation-sidebar').dataset.layout==='drawer'&&Math.abs(#{ui}.querySelector('.annotation-sidebar').scrollTop-#{drawer_top})<5")
  b.screenshot(File.join(out,'drawer-restored.png'))
  c.call('Emulation.setDeviceMetricsOverride',width:1440,height:1000,deviceScaleFactor:1,mobile:false)
  c.wait_for("#{ui}.querySelector('.annotation-sidebar').dataset.layout==='aligned'")

  # A root-wide hash change for another page is not an edit of this document.
  other=File.join(fixture,'pages/other.html')
  write_fixture.call(other,File.read(other)+"\n<!-- synthetic other page build -->")
  load=c.evaluate('window.refreshFixtureLoad')
  same_load.call('An unrelated page build cannot reload a historical changed annotation',load)
  thread.call('annotation-refresh','running','Synthetic question is answering.')
  sync.call
  c.wait_for("#{ui}.querySelector('#annotation-state').textContent.includes('回复中')")
  thread.call('annotation-refresh','completed','Synthetic question answered without modifying source.')
  same_load.call('A pure question completion does not reload despite an unrelated build change',load)
  mark_changed.call('annotation-other')
  thread.call('annotation-other','completed','Other page edit completed.')
  same_load.call('A newly changed annotation belonging to another page cannot reload this page',load)

  # Changed is written before the worker finishes; wait for its actual completion.
  start_edit.call
  same_load.call('Changed metadata and a new build wait while the edit conversation is running',load)
  complete_edit.call
  wait_reload.call(load)
  same_load.call('A verified edit causes exactly one navigation, with no historical reload loop',load+1)
  b.screenshot(File.join(out,'automatic-refresh.png'))

  fill.call('Keep this unsent reply while the page changes.')
  c.evaluate("window.protectedField=#{ui}.querySelector('#annotation-followup')")
  load=c.evaluate('window.refreshFixtureLoad')
  start_edit.call;complete_edit.call
  c.wait_for("(()=>{const button=#{ui}.querySelector('[data-action=annotation-reload]');return button&&!button.hidden})()")
  same_load.call('An unsent reply defers automatic refresh and keeps a pending update control',load)
  check.call('Deferred refresh preserves the exact composing field, focus and reply text',"#{ui}.querySelector('#annotation-followup')===window.protectedField&&#{ui}.activeElement===window.protectedField&&window.protectedField.value==='Keep this unsent reply while the page changes.'")
  click.call('[data-action=annotation-reload]')
  check.call('Explicit refresh also preserves an unsent reply rather than discarding it',"window.refreshFixtureLoad===#{load}&&#{ui}.querySelector('#annotation-followup').value==='Keep this unsent reply while the page changes.'")
  c.evaluate("window.protectedField.value='';window.protectedField.dispatchEvent(new Event('input',{bubbles:true,composed:true}));window.protectedField.blur()")
  sync.call;wait_reload.call(load)

  # An empty IME composition has no ordinary input value, so it needs its own guard.
  load=c.evaluate('window.refreshFixtureLoad')
  c.evaluate("window.imeField=#{ui}.querySelector('#annotation-followup');window.imeField.focus();window.imeField.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true,composed:true}))")
  start_edit.call;complete_edit.call
  c.wait_for("(()=>{const button=#{ui}.querySelector('[data-action=annotation-reload]');return button&&!button.hidden})()")
  same_load.call('Active IME composition defers refresh even before committed input exists',load)
  c.evaluate("window.imeField.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,composed:true}));window.imeField.blur()")
  sync.call;wait_reload.call(load)

  # A new draft uses the existing localStorage evidence source, not view storage.
  load=c.evaluate('window.refreshFixtureLoad')
  c.evaluate("(()=>{const range=document.createRange();range.selectNodeContents(document.querySelector('#other-target'));getSelection().removeAllRanges();getSelection().addRange(range);document.dispatchEvent(new Event('selectionchange'))})()")
  c.wait_for("#{ui}.querySelector('[data-action=annotation-create]')")
  click.call('[data-action=annotation-create]')
  c.wait_for("#{ui}.querySelector('#annotation-input')")
  c.evaluate("#{ui}.querySelector('#annotation-input').focus()")
  c.call('Input.insertText',text:'Retain my unsent new annotation.')
  start_edit.call;complete_edit.call
  c.wait_for("(()=>{const button=#{ui}.querySelector('[data-action=annotation-reload]');return button&&!button.hidden})()")
  same_load.call('A new unsent annotation draft defers automatic refresh',load)
  check.call('The draft text and original selection remain available during the update',"#{ui}.querySelector('#annotation-input').value==='Retain my unsent new annotation.'&&#{ui}.querySelector('.annotation-card[data-draft=true] .annotation-quote').textContent.includes('A second nearby sentence')")
  click.call('[data-action=annotation-discard]')
  activate.call('annotation-refresh')
  sync.call;wait_reload.call(load)

  # Pending confirmation is loaded through the public browser storage contract.
  c.evaluate(<<~JS)
    localStorage.setItem('prototype.review.annotationRequests',JSON.stringify({'annotation-refresh:annotation-message':{annotationId:'annotation-refresh',messageId:'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa01',text:'Pending saved-only followup.',autoReply:false}}));
    localStorage.setItem('prototype.review.annotationChats',JSON.stringify({'annotation-refresh':'Pending saved-only followup.'}));
  JS
  c.call('Page.reload');ready.call
  c.wait_for("#{ui}.querySelector('#annotation-followup')?.disabled")
  load=c.evaluate('window.refreshFixtureLoad')
  start_edit.call;complete_edit.call
  c.wait_for("(()=>{const button=#{ui}.querySelector('[data-action=annotation-reload]');return button&&!button.hidden})()")
  same_load.call('A pending send confirmation prevents navigation and request replay',load)
  check.call('Pending send retains its content and immutable disabled composer',"#{ui}.querySelector('#annotation-followup').value==='Pending saved-only followup.'&&#{ui}.querySelector('#annotation-followup').disabled")
  click.call('[data-action=annotation-message]')
  c.wait_for("!#{ui}.querySelector('#annotation-followup')?.disabled")
  sync.call;wait_reload.call(load)

  # Do not discard an unrelated consumer form while an annotation edit finishes.
  c.evaluate("document.querySelector('#ordinary-input').focus();document.querySelector('#ordinary-input').select()")
  c.call('Input.insertText',text:'Unsaved consumer form data')
  load=c.evaluate('window.refreshFixtureLoad')
  start_edit.call;complete_edit.call
  c.wait_for("(()=>{const button=#{ui}.querySelector('[data-action=annotation-reload]');return button&&!button.hidden})()")
  same_load.call('Consumer form input defers page reload after a completed annotation edit',load)
  check.call('Consumer form contents remain intact',"document.querySelector('#ordinary-input').value==='Unsaved consumer form data'")
  # This explicit browser reload ends the test-owned form draft; never click a job action.
  c.call('Page.reload');ready.call
  c.wait_for("#{ui}.querySelector('.annotation-card[data-id=annotation-refresh] #annotation-followup')")

  load=c.evaluate('window.refreshFixtureLoad')
  c.evaluate("window.realStorageSetItem=Storage.prototype.setItem;Storage.prototype.setItem=function(key,value){if(String(key).startsWith('prototype.review.annotationView'))throw new DOMException('Synthetic full view storage','QuotaExceededError');return window.realStorageSetItem.call(this,key,value)}")
  start_edit.call;complete_edit.call
  c.wait_for("(()=>{const button=#{ui}.querySelector('[data-action=annotation-reload]');return button&&!button.hidden})()")
  same_load.call('Failed view-state persistence prevents an automatic reload',load)
  c.evaluate('Storage.prototype.setItem=window.realStorageSetItem')
  sync.call;wait_reload.call(load)

  # Fresh context navigation must not restore another page's current card.
  c.call('Page.navigate',url:base+'other.html');ready.call
  check.call('View storage is scoped to the page identity',"!#{ui}.querySelector('.annotation-card[data-id=annotation-refresh] #annotation-followup')")

  ['shared','disabled'].each do |environment|
    data_dir=File.join(fixture,environment+'-data')
    FileUtils.mkdir_p(File.join(data_dir,'annotation-threads'))
    records=JSON.parse(File.read(File.join(fixture,'data/annotations.json')))
    write_fixture.call(File.join(data_dir,'annotations.json'),JSON.generate(records))
    FileUtils.cp(File.join(thread_dir,'annotation-refresh.json'),File.join(data_dir,'annotation-threads/annotation-refresh.json'))
    url=ENV.fetch('ANNOTATIONS_'+environment.upcase+'_URL')
    c.call('Page.navigate',url:url);ready.call
    click.call('[data-action=annotations]') unless c.evaluate("!!#{ui}.querySelector('.annotation-sidebar')")
    c.wait_for("#{ui}.querySelector('.annotation-card[data-id=annotation-refresh]')")
    activate.call('annotation-refresh')
    load=c.evaluate('window.refreshFixtureLoad')
    rebuild.call
    mark_changed.call
    same_load.call("#{environment} mode never reloads automatically for changed content",load)
    check.call("#{environment} mode keeps Agent disabled", "#{ui}.querySelector('#annotation-agent-toggle').disabled")
  end
  c.call('Page.navigate',url:ENV.fetch('ANNOTATIONS_OFFLINE_URL'));ready.call
  load=c.evaluate('window.refreshFixtureLoad')
  offline_path=File.join(fixture,'offline/index.html')
  write_fixture.call(offline_path,File.read(offline_path)+"\n<!-- synthetic offline rebuild -->")
  same_load.call('Offline mode never reloads automatically',load)

  raise 'Legacy review evidence changed' unless File.binread(File.join(fixture,'data/comments.json'))==legacy
  rpc_path=File.join(fixture,'rpc.jsonl')
  rpc=File.exist?(rpc_path) ? File.readlines(rpc_path).map{|line|JSON.parse(line)} : []
  raise 'Refresh dispatched or resumed an Agent task' if rpc.any?{|row|['thread/start','thread/resume','turn/start'].include?(row['method'])}
  errors=c.events.select{|event|event['method']=='Runtime.exceptionThrown'}
  raise 'Browser runtime exception' unless errors.empty?
  checks<<'No Agent dispatch, original review mutation or browser runtime exception'
  File.write(File.join(out,'result.json'),JSON.pretty_generate(ok:true,checks:checks,runtimeErrors:errors))
  puts JSON.generate(ok:true,checks:checks.length)
ensure
  b.close
end
