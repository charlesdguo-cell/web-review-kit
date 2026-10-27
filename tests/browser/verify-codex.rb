require_relative '../support/browser'
root=File.expand_path('../..',__dir__);out=File.join(root,'artifacts/validation-review-codex');FileUtils.mkdir_p(out)
base=ENV.fetch('PROTOTYPE_CODEX_TEST_URL');fixture=ENV.fetch('PROTOTYPE_CODEX_FIXTURE')
b=PrototypeBrowser.new;c=b.cdp;checks=[]
ui="document.querySelector('#prototype-review').shadowRoot"
check=lambda{|name,expr|raise name unless c.evaluate(expr);checks<<name;puts 'PASS '+name}
click=lambda do |selector|
 xy=c.evaluate("(()=>{const el=#{ui}.querySelector(#{selector.to_json});if(!el)throw Error('Missing review control '+#{selector.to_json});const r=el.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
 c.call('Input.dispatchMouseEvent',type:'mousePressed',x:xy['x'],y:xy['y'],button:'left',clickCount:1)
 c.call('Input.dispatchMouseEvent',type:'mouseReleased',x:xy['x'],y:xy['y'],button:'left',clickCount:1)
end
status=lambda do |value|
 c.wait_for("fetch('/__review/codex').then(r=>r.json()).then(d=>d.job?.status===#{value.to_json})",20)
 c.wait_for("#{ui}.querySelector('[data-action=codex]')?.textContent.includes(#{ {'running'=>'处理中','cancelled'=>'已停止','failed'=>'未完成','completed'=>'已完成'}[value].to_json})||#{ui}.querySelector('.codex-task strong')?.textContent.includes(#{ {'running'=>'正在处理','cancelled'=>'已停止','failed'=>'未完成','completed'=>'本轮已完成'}[value].to_json})",10)
end
open_panel=lambda do
 click.call('[data-action=codex-details]') if c.evaluate("!!#{ui}.querySelector('[data-action=codex-details]')") && !c.evaluate("!!#{ui}.querySelector('.codex-task')")
 click.call('[data-action=codex]') unless c.evaluate("!!#{ui}.querySelector('.codex-task')")
 c.wait_for("!!#{ui}.querySelector('#codex-input')")
end
input=lambda do |text|
 c.wait_for("!!#{ui}.querySelector('#codex-input')&&!#{ui}.querySelector('#codex-input').disabled")
 c.evaluate("#{ui}.querySelector('#codex-input').focus()")
 c.call('Input.insertText',text:text)
 c.wait_for("#{ui}.querySelector('#codex-input').value.endsWith(#{text.to_json})&&!#{ui}.querySelector('[data-action=codex-send]').disabled")
end
begin
 $stdout.sync=true
 c.call('Emulation.setDeviceMetricsOverride',width:1440,height:900,deviceScaleFactor:1,mobile:false)
 c.call('Page.navigate',url:base);c.wait_for("!!window.PrototypeReview&&#{ui}.querySelector('.count')?.textContent==='2'")
 c.wait_for("!!#{ui}.querySelector('link').sheet&&!#{ui}.querySelector('[data-action=codex]').disabled")
 check.call('最新评论已处理时，仍可派发其他页面的旧待处理评论',"#{ui}.querySelector('[data-action=codex]').title.includes('全部 1 条')")
 click.call('[data-action=toggle]');c.step({'action'=>'click','selector'=>'#message'})
 c.wait_for("!!#{ui}.querySelector('#note-input')")
 check.call('未保存评论时禁用任务入口',"#{ui}.querySelector('[data-action=codex]').disabled")
 c.evaluate("#{ui}.querySelector('#note-input').focus()")
 c.call('Input.insertText',text:'新增评论与旧评论一起处理。')
 click.call('[data-action=save]')
 c.wait_for("!#{ui}.querySelector('#note-input')&&#{ui}.querySelector('.count').textContent==='3'",30)
 c.wait_for("!#{ui}.querySelector('[data-action=codex]').disabled")
 check.call('保存新评论不会自动启动任务',"fetch('/__review/codex').then(r=>r.json()).then(d=>d.job===null)")
 File.write(File.join(fixture,'behavior'),'slow')
 click.call('[data-action=codex]');status.call('running')
 check.call('派发后只显示工具栏进度，不自动弹出任务窗口',"!#{ui}.querySelector('.codex-task')&&document.documentElement.hasAttribute('data-prototype-review-active')&&activated===0")
 job_before=c.evaluate("fetch('/__review/codex').then(r=>r.json()).then(d=>d.job.id)")
 open_panel.call
 check.call('点击进度展开对话，并收起评论列表',"#{ui}.querySelector('#list').children.length===0&&#{ui}.querySelector('.codex-task strong').textContent.includes('2 条评论')")
 check.call('任务面板锚定工具栏上方且保持紧凑宽度',"(()=>{const a=#{ui}.querySelector('.bar').getBoundingClientRect(),b=#{ui}.querySelector('#codex-panel').getBoundingClientRect();return b.bottom<=a.top&&a.top-b.bottom<12&&b.width<=440&&Math.abs(b.left+b.width/2-a.left-a.width/2)<2})()")
 c.wait_for("fetch('/__review/codex').then(r=>r.json()).then(d=>d.job.threadId==='fixture-thread')")
 invocation=JSON.parse(File.read(File.join(fixture,'invocation.json')))
 raise 'Wrong batch' unless invocation['prompt'].include?('新增评论与旧评论一起处理。')&&invocation['prompt'].include?('其他页面的旧待处理评论')&&!invocation['prompt'].include?('已处理的最新评论')
 checks<<'全部待处理评论入批，已修改项排除'
 input.call('请保持现有配色')
 c.evaluate("window.chatField=#{ui}.querySelector('#codex-input');window.nativeFetch=window.fetch;window.dropReply=true;window.fetch=async(...args)=>{const r=await window.nativeFetch(...args);if(String(args[0]).endsWith('codex/message')&&window.dropReply){window.dropReply=false;throw Error('模拟发送结果断网')}return r;}")
 click.call('[data-action=codex-send]')
 c.wait_for("#{ui}.querySelector('#codex-chat-error')?.textContent.includes('模拟发送结果断网')")
 check.call('发送响应丢失时保留原输入，可重试',"#{ui}.querySelector('#codex-input').value==='请保持现有配色'")
 c.call('Page.reload');c.wait_for("!!#{ui}.querySelector('.codex-launch.running')")
 open_panel.call
 c.evaluate("window.chatField=#{ui}.querySelector('#codex-input')")
 click.call('[data-action=codex-send]')
 c.wait_for("#{ui}.querySelector('#codex-input')?.value===''&&#{ui}.querySelector('#codex-thread').textContent.includes('已收到补充要求')")
 check.call('运行中补充送入原任务，断网后刷新重试只接收一次',"fetch('/__review/codex').then(r=>r.json()).then(d=>d.job.id===#{job_before.to_json}&&d.job.status==='running'&&d.job.messages.filter(m=>m.role==='user').length===1)")
 input.call('还未发送的补充要求')
 c.wait_for("#{ui}.querySelector('#codex-thread').textContent.includes('已送达')")
 check.call('轮询不替换输入框或丢失草稿和焦点',"#{ui}.querySelector('#codex-input')===window.chatField&&#{ui}.activeElement===window.chatField&&window.chatField.value==='还未发送的补充要求'")
 click.call('[data-action=list]')
 check.call('评论列表与任务对话互斥',"!#{ui}.querySelector('.codex-task')&&!!#{ui}.querySelector('.comments')")
 open_panel.call
 check.call('重新展开保留未发送的文字',"#{ui}.querySelector('#codex-input').value==='还未发送的补充要求'")
 file=File.join(fixture,'data/comments.json');reviews=JSON.parse(File.read(file))
 reviews[0].merge!('status'=>'changed','updatedAt'=>'finished-old')
 reviews<<reviews[0].merge('id'=>'fixture-comment-004','number'=>4,'status'=>'open','text'=>'运行期间新增，留到下一批','updatedAt'=>'new-four')
 File.write(file+'.fixture',JSON.generate(reviews));File.rename(file+'.fixture',file)
 c.wait_for("#{ui}.querySelector('.codex-summary')?.textContent.includes('已处理 1/2')")
 check.call('逐条同步进度，新评论不加入当前批次',"#{ui}.querySelectorAll('.codex-comments li').length===2&&!#{ui}.querySelector('.codex-comments').textContent.includes('#4')")
 b.screenshot(File.join(out,'running.png'))
 click.call('[data-action=list]');click.call('[data-action=filter]')
 c.wait_for("Array.from(#{ui}.querySelectorAll('.comment')).some(e=>e.textContent.includes('#1')&&e.querySelector('.comment-head span')?.textContent==='待验收')")
 checks<<'处理中已修改的评论同步到列表，不再仍显示待处理'
 c.call('Page.reload');c.wait_for("!!#{ui}.querySelector('.codex-launch.running')")
 check.call('刷新后进度恢复，保持面板收起',"!#{ui}.querySelector('.codex-task')")
 open_panel.call
 check.call('刷新后恢复同一任务、聊天记录与输入草稿',"#{ui}.querySelector('#codex-input').value==='还未发送的补充要求'&&#{ui}.querySelector('#codex-thread').textContent.includes('已收到补充要求')")
 click.call('[data-action=codex-stop]');status.call('cancelled')
 check.call('停止保留修改与重试入口',"!!#{ui}.querySelector('[data-action=codex-retry]')")
 File.write(File.join(fixture,'behavior'),'fail')
 click.call('[data-action=codex-retry]');status.call('failed')
 check.call('失败明确显示未完成，不冒充成功',"#{ui}.querySelector('.codex-progress').textContent.includes('执行未完成')")
 invocation=JSON.parse(File.read(File.join(fixture,'invocation.json')))
 raise 'Retry included finished or new comments' unless invocation['prompt'].include?('新增评论与旧评论一起处理。')&&!invocation['prompt'].include?('其他页面的旧待处理评论')&&!invocation['prompt'].include?('运行期间新增，留到下一批')
 checks<<'重试只处理原批未完成项'
 File.write(File.join(fixture,'behavior'),'complete')
 click.call('[data-action=codex-retry]');status.call('completed')
 c.wait_for("#{ui}.querySelector('[data-action=codex]').textContent==='交给 Codex · 1'")
 check.call('有新评论时仍保留单独的当前任务对话入口',"!!#{ui}.querySelector('[data-action=codex-details]')")
 click.call('[data-action=codex]')
 c.wait_for("fetch('/__review/codex').then(r=>r.json()).then(d=>d.job.comments.length===1&&d.job.comments[0].number===4&&d.job.status==='completed')")
 c.wait_for("#{ui}.querySelector('[data-action=codex]').textContent==='已完成 · 查看结果'")
 open_panel.call
 check.call('下一批只处理新评论并展示结果',"#{ui}.querySelector('.codex-comments').textContent.includes('#4')&&#{ui}.querySelector('#codex-thread').textContent.includes('临时任务完成')")
 completed_id=c.evaluate("fetch('/__review/codex').then(r=>r.json()).then(d=>d.job.id)")
 input.call('继续解释刚才的修改')
 c.call('Input.dispatchKeyEvent',type:'keyDown',key:'Enter',code:'Enter',modifiers:4,windowsVirtualKeyCode:13)
 c.call('Input.dispatchKeyEvent',type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13)
 c.wait_for("#{ui}.querySelector('#codex-thread').textContent.includes('同一会话继续：继续解释刚才的修改')")
 status.call('completed')
 check.call('结束后可用快捷键继续原会话，而非新建评论任务',"fetch('/__review/codex').then(r=>r.json()).then(d=>d.job.id===#{completed_id.to_json}&&d.job.comments[0].number===4)")
 click.call('[data-action=codex-reload]');c.wait_for("!!#{ui}.querySelector('[data-action=codex]')&&!#{ui}.querySelector('[data-action=codex]').disabled")
 open_panel.call
 check.call('刷新原型后仍可查看对话结果',"#{ui}.querySelector('#codex-thread').textContent.includes('继续解释刚才的修改')")
 c.call('Emulation.setDeviceMetricsOverride',width:390,height:844,deviceScaleFactor:1,mobile:false)
 click.call('[data-action=toggle]')
 c.wait_for("(()=>{const a=#{ui}.querySelector('.bar').getBoundingClientRect(),b=#{ui}.querySelector('#codex-panel').getBoundingClientRect();return b.bottom<=a.top&&b.left>=0&&b.right<=innerWidth&&b.top>=0})()")
 check.call('窄屏对话与工具栏不重叠，发送区可见',"(()=>{const a=#{ui}.querySelector('[data-action=codex-send]').getBoundingClientRect();return a.top>0&&a.bottom<innerHeight})()")
 b.screenshot(File.join(out,'mobile-result.png'))
 c.evaluate("#{ui}.querySelector('#codex-input').focus()")
 c.call('Input.dispatchKeyEvent',type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27)
 c.call('Input.dispatchKeyEvent',type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27)
 check.call('Esc 只收起面板，保留评论模式并归还焦点',"!#{ui}.querySelector('.codex-task')&&document.documentElement.hasAttribute('data-prototype-review-active')&&#{ui}.activeElement?.dataset.action==='codex'")
 click.call('[data-action=toggle]');open_panel.call
 c.step({'action'=>'click','selector'=>'#message'})
 check.call('点击页面外部收起面板，页面原有操作正常',"!#{ui}.querySelector('.codex-task')&&activated===1")
 errors=c.events.select{|e|e['method']=='Runtime.exceptionThrown'};raise errors.to_json unless errors.empty?
 File.write(File.join(out,'results.json'),JSON.pretty_generate(checks:checks,runtime_errors:errors));puts "#{checks.length} checks passed; no runtime exceptions."
rescue=>e
 b.screenshot(File.join(out,'failure.png')) rescue nil
 File.write(File.join(out,'failure.txt'),e.full_message);raise
ensure
 b.close
end
