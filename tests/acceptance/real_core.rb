# Explicitly opt in: this starts a REAL Codex worker, only in the synthetic project.
require_relative '../support/browser'
require 'net/http'
require 'digest'
root=File.expand_path(ENV.fetch('VALIDATION_PROJECT'))
raise 'Only the independent validation workspace is authorized' unless root=='/Users/charles/Documents/codex/web-review-kit-validation'
raise 'Real-worker opt-in required' unless ENV['ALLOW_REAL_CODEX']=='1'
base='http://127.0.0.1:8791/'
health=JSON.parse(Net::HTTP.get(URI(base+'__review/health')))
raise 'Wrong service' unless health['projectId']=='field-notes-validation' && health['toolVersion']=='0.1.0-rc.3'
out=File.join(root,'artifacts/acceptance');FileUtils.mkdir_p(out)
raise 'Refuse to reuse nonempty comments' unless JSON.parse(Net::HTTP.get(URI(base+'__review/comments')))['comments'].empty?
b=PrototypeBrowser.new;c=b.cdp;checks=[];ui="document.querySelector('#prototype-review').shadowRoot"
click=lambda{|sel| c.evaluate("#{ui}.querySelector(#{sel.to_json}).click()")}
check=lambda{|name,value| raise name unless value;checks<<name;puts 'PASS '+name}
read=lambda{|path|JSON.parse(Net::HTTP.get(URI(base+path)))}
open_panel=lambda do
 click.call('[data-action=codex-details]') if c.evaluate("!!#{ui}.querySelector('[data-action=codex-details]')") && !c.evaluate("!!#{ui}.querySelector('.codex-task')")
 click.call('[data-action=codex]') unless c.evaluate("!!#{ui}.querySelector('.codex-task')")
 c.wait_for("!!#{ui}.querySelector('#codex-input')")
end
fill=lambda do |text|
 c.wait_for("!!#{ui}.querySelector('#codex-input')&&!#{ui}.querySelector('#codex-input').disabled")
 c.evaluate("#{ui}.querySelector('#codex-input').focus()")
 c.call('Input.insertText',text:text)
 click.call('[data-action=codex-send]')
end
note=lambda do |selector,text,attachment|
 c.step({'action'=>'click','selector'=>selector})
 c.wait_for("!!#{ui}.querySelector('#note-input')")
 c.evaluate("#{ui}.querySelector('#note-input').focus()")
 c.call('Input.insertText',text:text)
 if attachment
 c.evaluate(<<~JS)
 (()=>{const canvas=document.createElement('canvas');canvas.width=96;canvas.height=48;const x=canvas.getContext('2d');x.fillStyle='#1c6455';x.fillRect(0,0,96,48);x.fillStyle='#dfd387';x.fillRect(8,8,80,32);const bytes=Uint8Array.from(atob(canvas.toDataURL().split(',')[1]),a=>a.charCodeAt(0)),data=new DataTransfer();data.items.add(new File([bytes],'field-note-reference.png',{type:'image/png'}));#{ui}.querySelector('#note-input').dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,composed:true,cancelable:true}));})()
 JS
 c.wait_for("#{ui}.querySelectorAll('.attachment-drafts img').length===1")
 end
 c.wait_for("!#{ui}.querySelector('[data-action=save]').disabled")
 click.call('[data-action=save]')
 c.wait_for("!#{ui}.querySelector('#note-input')",30)
end
begin
 $stdout.sync=true
 c.call('Emulation.setDeviceMetricsOverride',width:1360,height:960,deviceScaleFactor:1,mobile:false)
 c.call('Page.navigate',url:base)
 c.wait_for("!!#{ui}.querySelector('[data-action=toggle]')")
 # Exercise the consumer controls before review mode intercepts the page.
 c.evaluate("document.querySelector('#filter').value='tidal';document.querySelector('#filter').dispatchEvent(new Event('input'))")
 check.call('consumer input filters observations',c.evaluate("document.querySelector('.text-card').hidden"))
 c.evaluate("document.querySelector('#filter').value='';document.querySelector('#filter').dispatchEvent(new Event('input'));document.querySelector('#about-open').click()")
 check.call('consumer dialog opens',c.evaluate("document.querySelector('#about').open"))
 c.call('Input.dispatchKeyEvent',type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27)
 c.call('Input.dispatchKeyEvent',type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27)
 c.wait_for("!document.querySelector('#about').open")
 b.screenshot(File.join(out,'collection-before.png'))
 click.call('[data-action=toggle]')
 note.call('#page-title','请将本页主标题 Collection 改成 Field collection。仅按项目 guidance 修改 src/index.html，保留布局和交互，执行配置中的构建与检查并保留本评论原截图、附图和定位；验证后标 changed，不要 resolved。',true)
 initial=read.call('__review/comments')['comments'];raise 'Expected exactly one saved comment' unless initial.length==1
 File.write(File.join(out,'comment-1-frozen.json'),JSON.pretty_generate(initial.first))
 evidence=([initial.first['screenshot']]+initial.first['attachments'].map{|x|x['url']}).to_h{|url|[url,Digest::SHA256.hexdigest(Net::HTTP.get(URI(base+url.sub(%r{^/},''))))]}
 File.write(File.join(out,'evidence-before.json'),JSON.pretty_generate(evidence))
 check.call('browser UI saves screenshot and attachment',initial.first['screenshot'] && initial.first['attachments'].length==1)
 c.wait_for("!#{ui}.querySelector('[data-action=codex]').disabled")
 click.call('[data-action=codex]')
 c.wait_for("fetch('/__review/codex').then(r=>r.json()).then(d=>d.job&&['starting','running'].includes(d.job.status))",30)
 job=read.call('__review/codex')['job'];File.write(File.join(out,'initial-job.json'),JSON.pretty_generate(job))
 puts "REAL worker started #{job['id']}"
 # The next comment is submitted through the same live UI after the frozen job exists.
 note.call('#specimen-link','下一批处理：把详情页返回链接 Back to collection 改为 Explore collection。本条运行中新建，留在 open，当前批次不要处理。',false)
 check.call('new comment created during running batch',read.call('__review/comments')['comments'].length==2)
 open_panel.call
 fill.call('补充当前 #1：同时把首页现有 eyebrow 改为 Independent static project。不要处理运行中新建的 #2，也不要改变页面结构。')
 c.wait_for("fetch('/__review/codex').then(r=>r.json()).then(d=>d.job.messages.some(m=>m.role==='user'))",20)
 b.screenshot(File.join(out,'real-worker-running.png'))
 puts 'Supplement sent; waiting for real model completion'
 c.wait_for("fetch('/__review/codex').then(r=>r.json()).then(d=>['completed','failed','cancelled'].includes(d.job.status))",900)
 final=read.call('__review/codex')['job'];File.write(File.join(out,'first-completed-job.json'),JSON.pretty_generate(final))
 raise "Worker status #{final['status']}: #{final['error']}" unless final['status']=='completed'
 comments=read.call('__review/comments')['comments'];one,two=comments
 check.call('actual worker marks original comment changed',one['status']=='changed' && !one['resolution'].to_s.empty?)
 check.call('running-time comment stays open for next batch',two['status']=='open')
 source=File.read(File.join(root,'src/index.html'))
 check.call('source contains requested title and supplement',source.include?('>Field collection</h1>') && source.include?('>Independent static project</p>'))
 request=JSON.parse(File.read(File.join(root,'.review/jobs',job['id'],'request.json')))
 check.call('frozen request contains only original comment',request['comments'].map{|x|x['id']}==[initial.first['id']])
 frozen=initial.first
 %w[id number text page anchor screenshot attachments createdAt].each{|key|raise "Original evidence field changed: #{key}" unless one[key]==frozen[key]}
 check.call('original body anchor screenshot attachments preserved',true)
 File.write(File.join(out,'comments-after-real-worker.json'),JSON.pretty_generate(comments))
 # Real same-thread continuation, with explicit no-change/no-new-batch instruction.
 evidence.each{|url,sha|raise 'Evidence bytes changed' unless Digest::SHA256.hexdigest(Net::HTTP.get(URI(base+url.sub(%r{^/},''))))==sha}
 thread=final['threadId'];raise 'Missing real thread ID' if thread.to_s.empty?
 prior_assistant_ids=final['messages'].select{|m|m['role']=='assistant'}.map{|m|m['id']}
 fill.call('请在原线程简短解释 #1 的标题和补充修改以及实际验证结果。本次只解释，不修改任何文件或评论，不处理 #2，不派发新任务。')
 c.wait_for("fetch('/__review/codex').then(r=>r.json()).then(d=>d.job.messages.filter(m=>m.role==='user').length===2)",30)
 c.wait_for("fetch('/__review/codex').then(r=>r.json()).then(d=>d.job.status==='completed'&&d.job.messages.some(m=>m.role==='assistant'&&!#{prior_assistant_ids.to_json}.includes(m.id)))",600)
 followed=read.call('__review/codex')['job']
 check.call('real completed-job follow-up retains job and thread',followed['id']==job['id'] && followed['threadId']==thread)
 File.write(File.join(out,'followup-job.json'),JSON.pretty_generate(followed))
 b.screenshot(File.join(out,'same-thread-result.png'))
 c.call('Page.navigate',url:base)
 c.wait_for("document.querySelector('#page-title')?.textContent==='Field collection'")
 b.screenshot(File.join(out,'collection-after.png'))
 c.call('Page.navigate',url:base+'specimen.html')
 c.wait_for("document.querySelector('#sample-audio')?.readyState>=1")
 check.call('synthetic audio metadata is readable',c.evaluate("document.querySelector('#sample-audio').duration===2"))
 c.step({'action'=>'click','selector'=>'#sample-audio'})
 c.evaluate("document.querySelector('#sample-audio').muted=true;document.querySelector('#sample-audio').play()")
 c.wait_for("document.querySelector('#sample-audio').currentTime>0")
 check.call('synthetic audio playback advances',true)
 b.screenshot(File.join(out,'detail-after.png'))
 errors=c.events.select{|e|e['method']=='Runtime.exceptionThrown'};raise errors.to_json unless errors.empty?
 File.write(File.join(out,'real-core-results.json'),JSON.pretty_generate(checks:checks,jobId:job['id'],threadId:thread,realCodex:true,runtimeErrors:errors))
 puts "#{checks.length} real core checks passed"
rescue=>e
 b.screenshot(File.join(out,'real-core-failure.png')) rescue nil
 File.write(File.join(out,'real-core-failure.txt'),e.full_message)
 raise
ensure
 b.close
end
