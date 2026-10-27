require_relative 'support/browser'
require_relative 'support/fixture_site'
require 'cgi'
root=File.expand_path('..',__dir__)
scratch=Dir.mktmpdir('review-projects-');site=File.join(scratch,'site');FileUtils.mkdir_p(site)
assets=File.join(site,'assets');FileUtils.mkdir_p(assets)
%w[review.js review.css html2canvas.min.js].each{|name|FileUtils.cp(File.join(root,'runtime',name),assets)}
legacy=%w[prototype.review.v1 prototype.review.codexDrafts prototype.review.codexRequests]
key=lambda{|namespace,kind|"prototype.review.#{namespace}.#{kind}"}
page=File.read(File.join(__dir__,'fixtures/projects/page.html')).sub('window.fixtureJob=', 'window.nativeFetch=window.fetch.bind(window);window.fixtureJob=')
write_page=lambda do |name,id,identity={},storage={}|
 attrs={'src'=>'/assets/review.js','data-project-id'=>id,'data-page-identity'=>JSON.generate(identity),'data-browser-storage'=>JSON.generate(storage),'data-codex'=>'true'}
 tag='<script data-prototype-review '+attrs.map{|k,v|k+'="'+CGI.escapeHTML(v)+'"'}.join(' ')+'></script>'
 File.write(File.join(site,name),page.sub('REVIEW_SCRIPT',tag))
end
write_page.call('index.html','alpha');write_page.call('beta.html','beta')
write_page.call('selected.html','query',{'strategy'=>'pathname','queryKeys'=>['mode','tag'],'includeHash'=>true})
write_page.call('default.html','default')
write_page.call('migrate.html','morsea',{}, {'namespace'=>'morsea','legacyKeys'=>legacy})
write_page.call('unapproved.html','unapproved')
socket=TCPServer.new('127.0.0.1',0);port=socket.addr[1];socket.close
log=File.join(scratch,'server.log');pid=Process.spawn('python3','-m','http.server',port.to_s,'--bind','127.0.0.1','--directory',site,out:log,err:[:child,:out])
b=nil;checks=[];failures=[];out=File.join(root,'artifacts/validation-projects');FileUtils.mkdir_p(out)
begin
 Timeout.timeout(10){loop{begin;break if Net::HTTP.get(URI("http://127.0.0.1:#{port}/")).include?('Synthetic project');rescue Errno::ECONNREFUSED;end;sleep 0.1}}
 b=PrototypeBrowser.new;c=b.cdp;ui="document.querySelector('#prototype-review').shadowRoot";$stdout.sync=true
 c.call('Emulation.setDeviceMetricsOverride',width:1200,height:900,deviceScaleFactor:1,mobile:false)
 visit=lambda{|path|c.call('Page.navigate',url:"http://127.0.0.1:#{port}/"+path);c.wait_for("!!window.PrototypeReview && !!#{ui}.querySelector('[data-action=codex]:not([disabled])')")}
 click=lambda{|selector|c.evaluate("#{ui}.querySelector(#{selector.to_json}).click()")}
 check=lambda{|name,expr|result=c.evaluate(expr);if result;checks<<name;puts 'PASS '+name;else;failures<<name;puts 'FAIL '+name;end}
 save=lambda do |text|
  click.call('[data-action=toggle]');c.step({'action'=>'click','selector'=>'#action'})
  c.wait_for("!!#{ui}.querySelector('#note-input')")
  c.evaluate("#{ui}.querySelector('#note-input').focus()");c.call('Input.insertText',text:text)
  click.call('[data-action=save]');c.wait_for("!#{ui}.querySelector('#note-input')",30)
 end
 draft=lambda do |text|
  click.call('[data-action=codex]');c.wait_for("!!#{ui}.querySelector('#codex-input')")
  c.evaluate("#{ui}.querySelector('#codex-input').focus()");c.call('Input.insertText',text:text)
  click.call('[data-action=codex-send]');c.wait_for("#{ui}.querySelector('#codex-chat-error')?.textContent==='Synthetic message failure'")
 end
 visit.call('index.html');save.call('Alpha comment');draft.call('Alpha draft')
 alpha_id=c.evaluate('messageIds[0]')
 visit.call('beta.html');click.call('[data-action=list]')
 comments_clean=c.evaluate("#{ui}.querySelectorAll('.comment').length===0")
 draft.call('Beta draft');beta_id=c.evaluate('messageIds[0]')
 check.call('同源项目隔离',<<~JS)
  #{comments_clean} && #{ui}.querySelector('#codex-input').value==='Beta draft' && #{alpha_id.to_json}!==#{beta_id.to_json} &&
  JSON.parse(localStorage.getItem(#{key.call('alpha','comments').to_json})||'[]')[0]?.text==='Alpha comment' &&
  JSON.parse(sessionStorage.getItem(#{key.call('alpha','codexDrafts').to_json})||'{}')['same-job']==='Alpha draft' &&
  JSON.parse(sessionStorage.getItem(#{key.call('beta','codexDrafts').to_json})||'{}')['same-job']==='Beta draft' &&
  JSON.parse(sessionStorage.getItem(#{key.call('alpha','codexRequests').to_json})||'{}')['same-job']?.id===#{alpha_id.to_json} &&
  JSON.parse(sessionStorage.getItem(#{key.call('beta','codexRequests').to_json})||'{}')['same-job']?.id===#{beta_id.to_json}
 JS
 visit.call('');click.call('[data-action=list]')
 check.call('首页身份归一',"#{ui}.querySelector('.comment p')?.textContent==='Alpha comment'")
 draft.call('');check.call('项目草稿及消息重试标识刷新后恢复',"#{ui}.querySelector('#codex-input').value==='Alpha draft' && messageIds[0]===#{alpha_id.to_json}")
 c.evaluate("window.imeField=#{ui}.querySelector('#codex-input');imeField.focus();imeField.setSelectionRange(2,2);imeField.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true,composed:true,data:'输入'}));fixtureJob.progress='IME polling fixture';imeField.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',metaKey:true,isComposing:true,bubbles:true,composed:true}));")
 c.wait_for("#{ui}.querySelector('.codex-progress').textContent==='IME polling fixture'")
 check.call('输入法组合中轮询保留输入节点焦点选区且不误发送',"#{ui}.querySelector('#codex-input')===imeField && #{ui}.activeElement===imeField && imeField.selectionStart===2 && imeField.value==='Alpha draft' && messageIds.length===1")
 c.evaluate("imeField.dispatchEvent(new CompositionEvent('compositionend',{bubbles:true,composed:true,data:'输入'}))")
 c.call('Emulation.setDeviceMetricsOverride',width:390,height:844,deviceScaleFactor:1,mobile:false)
 c.wait_for("(()=>{const r=#{ui}.querySelector('[data-action=codex-send]').getBoundingClientRect();return r.right<=innerWidth&&r.bottom<=innerHeight})()")
 check.call('窄屏失败草稿及发送区域保持可见',"(()=>{const r=#{ui}.querySelector('[data-action=codex-send]').getBoundingClientRect();return imeField.value==='Alpha draft' && r.left>=0 && r.right<=innerWidth && r.top>=0 && r.bottom<=innerHeight;})()")
 c.call('Emulation.setDeviceMetricsOverride',width:1200,height:900,deviceScaleFactor:1,mobile:false)
 visit.call('selected.html?ignored=secret&tag=b&mode=edit&tag=a#details');save.call('Selected URL')
 check.call('声明 query/hash 规范身份且保留完整 URL',<<~JS)
  (()=>{const record=JSON.parse(localStorage.getItem(#{key.call('query','comments').to_json})||'[]')[0];return record?.page.path==='/selected.html?mode=edit&tag=b&tag=a#details' && record.page.url===location.href && record.page.url.includes('ignored=secret');})()
 JS
 visit.call('selected.html?tag=b&ignored=other&tag=a&mode=edit#details');click.call('[data-action=list]')
 check.call('查询参数键顺序和未声明参数不改变身份',"#{ui}.querySelector('.comment p')?.textContent==='Selected URL'")
 visit.call('selected.html?mode=view&tag=b&tag=a#details');click.call('[data-action=list]')
 check.call('声明参数改变后分开页面评论',"#{ui}.querySelectorAll('.comment').length===0")
 visit.call('selected.html?mode=edit&tag=b&tag=a#other');click.call('[data-action=list]')
 check.call('声明 hash 改变后分开页面评论',"#{ui}.querySelectorAll('.comment').length===0")
 visit.call('default.html?mode=edit#one');save.call('Path only')
 visit.call('default.html?mode=view#two');click.call('[data-action=list]')
 check.call('未声明时仅 pathname 参与身份',"#{ui}.querySelector('.comment p')?.textContent==='Path only'")
 # Legacy records retain original paths, evidence and timestamps during an explicit copy.
 legacy_comment={id:'legacy-comment',number:1,text:'Legacy evidence',status:'open',createdAt:'old',updatedAt:'old',page:{path:'/migrate.html',url:'file:///original/migrate.html',title:'Legacy'},anchor:{selector:'#gone',label:'Gone'},attachments:[],screenshotData:'data:image/png;base64,original'}
 values=[JSON.generate([legacy_comment]),JSON.generate({'same-job'=>'Legacy draft'}),JSON.generate({'same-job'=>{id:'legacy-request',text:'Legacy draft'}})]
 c.evaluate("(()=>{#{legacy.zip(values).map{|k,v|"#{k.start_with?('prototype.review.codex') ? 'sessionStorage' : 'localStorage'}.setItem(#{k.to_json},#{v.to_json});"}.join}})()")
 visit.call('unapproved.html');click.call('[data-action=list]');click.call('[data-action=codex]')
 check.call('未授权项目不读取或接管旧键',"#{ui}.querySelectorAll('.comment').length===0 && #{ui}.querySelector('#codex-input').value==='' && localStorage.getItem(#{key.call('unapproved','comments').to_json})===null")
 visit.call('migrate.html');click.call('[data-action=list]')
 check.call('显式旧键复制保留原值与迁移标记',<<~JS)
  #{legacy.zip(values).map{|k,v|"#{k.start_with?('prototype.review.codex') ? 'sessionStorage' : 'localStorage'}.getItem(#{k.to_json})===#{v.to_json}"}.join(' && ')} &&
  localStorage.getItem(#{key.call('morsea','comments').to_json})===#{values[0].to_json} &&
  sessionStorage.getItem(#{key.call('morsea','codexDrafts').to_json})===#{values[1].to_json} &&
  sessionStorage.getItem(#{key.call('morsea','codexRequests').to_json})===#{values[2].to_json} &&
  Object.keys(localStorage).some(k=>k.startsWith(#{key.call('morsea','comments').to_json}+'.migrated.')) &&
  Object.keys(sessionStorage).filter(k=>k.includes('.migrated.')).length===2
 JS
 c.evaluate("localStorage.setItem(#{key.call('morsea','comments').to_json},JSON.stringify([{...JSON.parse(localStorage.getItem(#{key.call('morsea','comments').to_json}))[0],text:'Newer destination'}]))")
 visit.call('migrate.html');click.call('[data-action=list]')
 check.call('迁移不覆盖已有目标副本',"#{ui}.querySelector('.comment p')?.textContent==='Newer destination' && localStorage.getItem('prototype.review.v1')===#{values[0].to_json}")
 click.call('[data-action=locate]')
 check.call('失效锚点保留证据并显示定位提示',"!#{ui}.querySelector('#note-input') && #{ui}.querySelector('#notice').textContent.includes('原区块已变化') && #{ui}.querySelector('[data-action=snapshot]').textContent==='查看截图'")
 c.evaluate("localStorage.removeItem(#{key.call('morsea','comments').to_json})")
 visit.call('migrate.html');click.call('[data-action=list]')
 check.call('迁移标记阻止删除后再次接管旧数据',"#{ui}.querySelectorAll('.comment').length===0")
 # A prebuilt copy is replaced by one head-first configured HTTP injection.
 Process.kill('TERM',pid);Process.wait(pid);pid=nil
 FileUtils.mkdir_p(File.join(site,'nested'))
 File.write(File.join(site,'nested','page.html'), <<~HTML)
  <!doctype html><html><head><meta charset="utf-8"><title>Build injection fixture</title>
  <SCRIPT SRC="/assets/review.js" DATA-PROTOTYPE-REVIEW></SCRIPT>
  <script>window.appCaptureCount=0;window.addEventListener('click',()=>appCaptureCount++,true);</script>
  <script src="/team/review/bundle/first.js"></script><script src="/team/review/bundle/second.js"></script>
  </head><body><button id="injected-target">Synthetic injected target</button></body></html>
 HTML
 FileUtils.mkdir_p(File.join(site,'bundle'));%w[first second].each{|name|File.write(File.join(site,'bundle',name+'.js'),'')}
 dangerous='quoted"&<key'
 config={configVersion:1,projectId:'configured',toolVersion:File.read(File.join(root,'VERSION')).strip,
  webRoot:'.',dataDir:'../configured-data',jobsDir:'../configured-jobs',
  server:{host:'127.0.0.1',port:port,basePath:'/team/review',publicOrigins:['https://reviews.example.test']},
  pageIdentity:{strategy:'pathname',queryKeys:[dangerous],includeHash:true},browserStorage:{namespace:'safe"&<namespace',legacyKeys:[]},
  guidance:{requiredFiles:[],sourceRoots:[],buildCommands:[],checkCommands:[]},
  codex:{enabled:false,executable:'codex',approvalPolicy:'never',sandbox:'danger-full-access'}}
 File.write(File.join(site,'review.config.json'),JSON.generate(config))
 pid=Process.spawn('python3',File.join(__dir__,'fixtures/projects/serve.py'),site,out:log,err:[:child,:out])
 Timeout.timeout(10){loop{begin;break if Net::HTTP.get(URI("http://127.0.0.1:#{port}/team/review/__review/health")).include?('configured');rescue Errno::ECONNREFUSED;end;sleep 0.1}}
 c.call('Page.navigate',url:"http://127.0.0.1:#{port}/team/review/nested/page.html#evidence")
 c.wait_for("!!window.PrototypeReview && !!#{ui}.querySelector('link').sheet")
 check.call('构建注入再经 HTTP 仅一份工具且 JSON 属性安全编码',<<~JS)
  (()=>{const scripts=[...document.querySelectorAll('script')],tag=scripts.find(s=>s.hasAttribute('data-prototype-review'));return scripts.filter(s=>s.hasAttribute('data-prototype-review')).length===1 && document.querySelectorAll('#prototype-review').length===1 && tag.dataset.projectId==='configured' && JSON.parse(tag.dataset.pageIdentity).queryKeys[0]===#{dangerous.to_json} && JSON.parse(tag.dataset.browserStorage).namespace==='safe"&<namespace' && document.head.firstElementChild===tag && scripts.findIndex(s=>s.src.endsWith('first.js'))<scripts.findIndex(s=>s.src.endsWith('second.js'));})()
 JS
 click.call('[data-action=toggle]');c.evaluate('appCaptureCount=0');c.step({'action'=>'click','selector'=>'#injected-target'})
 check.call('前缀与子目录保留早期事件隔离',"appCaptureCount===0 && !!#{ui}.querySelector('#note-input') && #{ui}.querySelector('#note-input').value===''")
 c.evaluate("#{ui}.querySelector('#note-input').focus()");c.call('Input.insertText',text:'Prefixed evidence');click.call('[data-action=save]')
 c.wait_for("!#{ui}.querySelector('#note-input') && #{ui}.querySelector('.comment p')?.textContent==='Prefixed evidence'",30)
 check.call('前缀页面身份去除部署前缀且保留完整现场地址',"fetch('/team/review/__review/comments').then(r=>r.json()).then(d=>d.comments[0].page.path==='/nested/page.html#evidence' && d.comments[0].page.url===location.href && document.querySelector('script[data-prototype-review]').dataset.codex==='false')")
 exceptions=c.events.select{|event|event['method']=='Runtime.exceptionThrown'}
 raise JSON.generate(exceptions) unless exceptions.empty?
 File.write(File.join(out,'results.json'),JSON.pretty_generate({checks:checks,failures:failures,runtimeExceptions:exceptions}))
 puts "#{checks.length} checks passed; #{failures.length} failed"
 raise failures.join(', ') unless failures.empty?
ensure
 b.close if b;Process.kill('TERM',pid) if pid rescue nil;Process.wait(pid) if pid rescue nil;FileUtils.remove_entry(scratch)
end
