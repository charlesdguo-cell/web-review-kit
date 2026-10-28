require_relative '../support/browser'

# Opt-in configured query/hash identity, with only synthetic saved records and
# public conversation snapshots. Never dispatch a real or substitute model task.
root=File.expand_path('../..',__dir__)
out=File.join(root,'artifacts/validation-annotation-refresh-identity')
FileUtils.mkdir_p(out)
fixture=ENV.fetch('ANNOTATIONS_FIXTURE')
base=ENV.fetch('ANNOTATIONS_TEST_URL')
ui="document.querySelector('#prototype-review').shadowRoot"
paths={a:'/?section=a#one',b:'/?section=a#two',c:'/?section=b#two'}
b=PrototypeBrowser.new;c=b.cdp;checks=[]
ready=lambda{c.wait_for("window.PrototypeReview&&#{ui}.querySelector('link').sheet&&#{ui}.querySelector('[data-action=annotations]')")}
check=lambda{|name,expression|raise name unless c.evaluate(expression);checks<<name;puts "PASS #{name}"}
click=lambda{|selector|c.evaluate("#{ui}.querySelector(#{selector.to_json}).click()")}
open=lambda do |name|
  click.call('[data-action=annotations]') unless c.evaluate("!!#{ui}.querySelector('.annotation-sidebar')")
  c.wait_for("#{ui}.querySelector('.annotation-card[data-id=annotation-identity-#{name}]')")
  click.call(".annotation-card[data-id=annotation-identity-#{name}] [data-action=annotation-open]")
  c.wait_for("#{ui}.querySelector('.annotation-card[data-id=annotation-identity-#{name}] #annotation-followup')")
end
same_load=lambda do |name,load|
  3.times{c.evaluate("window.dispatchEvent(new Event('focus'))");sleep 0.6}
  check.call(name,"window.refreshFixtureLoad===#{load}")
end
change_build=lambda do |number|
  path=File.join(fixture,'pages/index.html')
  File.write(path+'.tmp',File.read(path)+"\n<!-- synthetic identity build #{number} -->")
  File.rename(path+'.tmp',path)
end
begin
  $stdout.sync=true
  c.call('Emulation.setDeviceMetricsOverride',width:1440,height:1000,deviceScaleFactor:1,mobile:false)
  c.call('Page.navigate',url:base+paths[:a].delete_prefix('/'));ready.call
  check.call('Configured identity includes the requested query key and hash',"(()=>{const p=JSON.parse(document.querySelector('[data-prototype-review]').dataset.pageIdentity);return p.includeHash&&p.queryKeys.includes('section')})()")
  c.evaluate(<<~JS)
    (async()=>{for(const [name,path,status] of [['a',#{paths[:a].to_json},'changed'],['a-resolved',#{paths[:a].to_json},'resolved'],['b',#{paths[:b].to_json},'changed'],['c',#{paths[:c].to_json},'changed']]){
      const el=document.querySelector('#target'),exact=el.textContent,annotation={id:'annotation-identity-'+name,text:'Synthetic identity '+name,status,page:{path,title:'Synthetic identity'},screenshotData:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLttAAAAABJRU5ErkJggg==',anchor:{kind:'text',selector:'#target',tag:'P',selectedText:exact,textRange:{start:0,end:exact.length,exact,prefix:'',suffix:''}},attachments:[]};
      const response=await fetch('/__review/annotations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({annotation,autoReply:false})});if(!response.ok)throw Error(await response.text());
    }})()
  JS
  dir=File.join(fixture,'data/annotation-threads');FileUtils.mkdir_p(dir)
  ['a','b','c'].each do |name|
    text=(1..15).map{|n|"Synthetic #{name} answer #{n}, retained only for this page identity."}.join("\n")
    File.write(File.join(dir,"annotation-identity-#{name}.json"),JSON.generate(id:"annotation-identity-#{name}",status:'completed',hasAgent:true,canChat:true,result:text,messages:[{id:'historical-'+name,role:'assistant',text:text,status:'sent',createdAt:1}]))
  end
  c.call('Page.reload');ready.call;open.call('a')
  click.call('[data-action=annotation-filter][data-filter=all]');open.call('a')
  click.call('.annotation-card[data-id=annotation-identity-a] [data-action=annotation-expand]')
  c.evaluate('scrollTo(0,620)');sleep 0.2
  a_scroll=c.evaluate('scrollY');load=c.evaluate('window.refreshFixtureLoad')
  change_build.call(1)
  c.evaluate("location.hash='two'")
  c.wait_for("location.hash==='#two'&&!#{ui}.querySelector('.annotation-card[data-id=annotation-identity-a]')")
  same_load.call('Hash navigation treats historical changed conversations as a new baseline',load)
  open.call('b')
  check.call('New hash identity has its own default filter and current conversation',"#{ui}.querySelectorAll('.annotation-card').length===1&&#{ui}.querySelector('#annotation-title').textContent.includes('未解决')&&!!#{ui}.querySelector('.annotation-card[data-id=annotation-identity-b] #annotation-followup')")
  c.call('Page.reload');ready.call
  c.wait_for("#{ui}.querySelector('.annotation-card[data-id=annotation-identity-b] #annotation-followup')")
  check.call('Manual reload restores the current hash identity view',"#{ui}.querySelectorAll('.annotation-card').length===1&&#{ui}.querySelector('#annotation-title').textContent.includes('未解决')")
  c.evaluate("location.hash='one'")
  c.wait_for("#{ui}.querySelector('.annotation-card[data-id=annotation-identity-a] #annotation-followup')")
  c.wait_for("Math.abs(scrollY-#{a_scroll})<5")
  check.call('Returning to a hash restores that identity filter, expansion and reading position',"#{ui}.querySelector('#annotation-title').textContent.includes('全部')&&#{ui}.querySelectorAll('.annotation-card').length===2&&!#{ui}.querySelector('.annotation-card[data-id=annotation-identity-a] .annotation-collapsed')&&Math.abs(scrollY-#{a_scroll})<5")
  load=c.evaluate('window.refreshFixtureLoad');change_build.call(2)
  c.evaluate("history.pushState({},'',#{paths[:c].to_json})")
  c.wait_for("location.search==='?section=b'&&!#{ui}.querySelector('.annotation-card[data-id=annotation-identity-a]')")
  same_load.call('Query pushState navigation resets the completion baseline without auto reload',load)
  open.call('c')
  c.call('Page.reload');ready.call
  c.wait_for("#{ui}.querySelector('.annotation-card[data-id=annotation-identity-c] #annotation-followup')")
  check.call('Manual reload restores the query identity rather than another page current card',"#{ui}.querySelectorAll('.annotation-card').length===1&&!#{ui}.querySelector('.annotation-card[data-id=annotation-identity-a]')&&!#{ui}.querySelector('.annotation-card[data-id=annotation-identity-b]')")
  # The same-document history entry precedes this reload and fires popstate.
  load=c.evaluate('window.refreshFixtureLoad')
  c.evaluate('history.back()')
  c.wait_for("location.search==='?section=a'&&location.hash==='#one'&&#{ui}.querySelector('.annotation-card[data-id=annotation-identity-a] #annotation-followup')")
  check.call('Back navigation restores the earlier identity without reloading or replaying messages',"window.refreshFixtureLoad===#{load}&&#{ui}.querySelector('#annotation-title').textContent.includes('全部')")
  rpc=File.join(fixture,'rpc.jsonl')
  raise 'Identity navigation activated an Agent' if File.exist?(rpc)&&File.readlines(rpc).map{|line|JSON.parse(line)}.any?{|r|['thread/start','thread/resume','turn/start'].include?(r['method'])}
  errors=c.events.select{|event|event['method']=='Runtime.exceptionThrown'}
  raise 'Identity browser runtime exception' unless errors.empty?
  File.write(File.join(out,'result.json'),JSON.pretty_generate(ok:true,checks:checks,runtimeErrors:errors))
  puts JSON.generate(ok:true,checks:checks.length)
ensure
  b.close
end
