require_relative '../support/browser'
require_relative '../support/fixture_site'

root = File.expand_path('../..', __dir__)
scratch = Dir.mktmpdir('prototype-review-test-')
site = File.join(scratch, 'site')
ReviewFixtureSite.create(site, root)
File.write(File.join(site, 'unregistered.html'), <<~HTML)
  <!doctype html><html><head><meta charset="utf-8"><title>通用页面验证</title>
  <style>body{font:18px sans-serif;margin:80px;background:#eff2f8;color:#17213a;height:2000px}section{padding:40px;background:white;width:650px}button,a,input{display:block;margin:18px 0;padding:12px}#blank{height:180px}svg{pointer-events:none}svg path{stroke:#634b98;stroke-width:10;fill:none}</style></head><body>
  <section id="card"><h1>新的页面，无需评论适配</h1><p id="words">准确选中文字，讨论文案修改。</p><button id="original">原有按钮</button><button disabled id="disabled">禁用按钮</button><input id="field" value="原来的输入"><a id="link" href="index.html">离开当前页面</a><div id="blank"></div><svg width="450" height="60"><path id="curve" d="M 10 30 L 440 30"/></svg></section>
  <script>window.counts={};['pointerdown','mousedown','click','keydown','dragstart','submit'].forEach(type=>window.addEventListener(type,()=>counts[type]=(counts[type]||0)+1,true));document.querySelector('#original').onclick=()=>window.activated=(window.activated||0)+1;</script>
  </body></html>
HTML
socket = TCPServer.new('127.0.0.1', 0); port = socket.addr[1]; socket.close
log = File.join(scratch,'server.log')
pid = Process.spawn('python3',File.join(root,'runtime/server.py'),'--root',site,'--data',File.join(scratch,'data'),'--port',port.to_s,out:log,err:[:child,:out])
b = nil
checks=[]
out=File.join(root,'artifacts/validation-review');FileUtils.mkdir_p(out)
begin
  Timeout.timeout(10) do
    loop do
      begin;break if Net::HTTP.get(URI("http://127.0.0.1:#{port}/__review/health")).include?('prototype-review');rescue Errno::ECONNREFUSED;end
      sleep 0.1
    end
  end
  b=PrototypeBrowser.new;c=b.cdp;$stdout.sync=true
  c.call('Emulation.setDeviceMetricsOverride',width:1440,height:980,deviceScaleFactor:1,mobile:false)
  c.call('Network.enable')
  base="http://127.0.0.1:#{port}/"
  review="document.querySelector('#prototype-review').shadowRoot"
  check=lambda do |name,expression|
    result=c.evaluate(expression);raise "#{name}: #{result.inspect}" unless result
    checks<<name;puts "PASS #{name}"
  end
  navigate=lambda do |page|
    c.call('Page.navigate',url:base+page);c.wait_for("document.readyState==='complete' && !!window.PrototypeReview && !!#{review}.querySelector('[data-action=toggle]')")
  end
  ui_click=lambda do |selector|
    xy=c.evaluate("(()=>{const e=#{review}.querySelector(#{JSON.generate(selector)});if(!e)throw Error('No review target: '+#{JSON.generate(selector)});e.scrollIntoView({block:'nearest'});const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
    c.call('Input.dispatchMouseEvent',type:'mouseMoved',x:xy['x'],y:xy['y'])
    c.call('Input.dispatchMouseEvent',type:'mousePressed',x:xy['x'],y:xy['y'],button:'left',clickCount:1)
    c.call('Input.dispatchMouseEvent',type:'mouseReleased',x:xy['x'],y:xy['y'],button:'left',clickCount:1)
    sleep 0.15
  end
  click=lambda{|selector|c.step({'action'=>'click','selector'=>selector})}
  drag=lambda do |x,y,ex,ey|
    c.call('Input.dispatchMouseEvent',type:'mouseMoved',x:x,y:y)
    c.call('Input.dispatchMouseEvent',type:'mousePressed',x:x,y:y,button:'left',clickCount:1)
    5.times{|i|c.call('Input.dispatchMouseEvent',type:'mouseMoved',x:x+(ex-x)*(i+1)/5.0,y:y+(ey-y)*(i+1)/5.0,buttons:1)}
    c.call('Input.dispatchMouseEvent',type:'mouseReleased',x:ex,y:ey,button:'left',clickCount:1)
    sleep 0.2
  end
  note=lambda do |text|
    c.evaluate("#{review}.querySelector('#note-input').focus()")
    c.call('Input.insertText',text:text)
  end
  navigate.call('unregistered.html')
  check.call('未登记的新 HTML 页面自动获得工具',"!!window.PrototypeReview && document.querySelectorAll('script[data-prototype-review]').length===1")
  click.call('#original');check.call('浏览模式保留正常点击',"activated===1")
  ui_click.call('[data-action=toggle]')
  c.evaluate('window.counts={};window.activated=0')
  click.call('#original')
  check.call('评论点选拦截按钮及 window 捕获监听器',"activated===0 && Object.keys(counts).length===0 && !!#{review}.querySelector('#note-input')")
  ui_click.call('[data-action=parent]')
  check.call('可扩大选中父级区块',"#{review}.querySelector('.note small').textContent==='元素评论' && #{review}.querySelector('[data-action=child]').disabled===false")
  ui_click.call('[data-action=child]')
  note.call('按钮文案需要更明确。')
  ui_click.call('[data-action=save]')
  c.wait_for("#{review}.querySelector('.comment p')?.textContent==='按钮文案需要更明确。'",30)
  records=JSON.parse(File.read(File.join(scratch,'data','comments.json')))
  raise 'Missing screenshot' unless File.size(File.join(scratch,'data','screenshots',records[0]['id']+'.png'))>1000
  check.call('评论和截图保存成功且评审输入未触发原页面',"Object.keys(counts).length===0")
  b.screenshot(File.join(out,'01-generic-comment.png'))
  ui_click.call('[data-action=edit]')
  c.evaluate("#{review}.querySelector('#note-input').select()")
  c.call('Input.insertText',text:'模拟保存响应丢失，重试保留修改。')
  c.evaluate(<<~JS)
    (()=>{const originalFetch=window.fetch;window.fetch=async(...args)=>{
      const response=await originalFetch(...args);
      if(args[1]?.method==='POST'){window.fetch=originalFetch;throw new TypeError('Failed to fetch');}
      return response;
    };})()
  JS
  ui_click.call('[data-action=save]')
  c.wait_for("#{review}.querySelector('.error')?.textContent.includes('未收到评审服务的保存确认')")
  check.call('保存响应丢失时明确提示并保留输入',"#{review}.querySelector('#note-input').value==='模拟保存响应丢失，重试保留修改。' && !#{review}.querySelector('[data-action=save]').disabled")
  committed=JSON.parse(File.read(File.join(scratch,'data','comments.json'))).first
  raise 'Lost-response fixture was not committed' unless committed['text']=='模拟保存响应丢失，重试保留修改。'
  ui_click.call('[data-action=save]')
  c.wait_for("!#{review}.querySelector('#note-input') && #{review}.querySelector('.comment p')?.textContent==='模拟保存响应丢失，重试保留修改。'")
  retried=JSON.parse(File.read(File.join(scratch,'data','comments.json')))
  raise 'Retry changed stored content, timestamp or screenshot' unless retried==[committed] && committed['screenshot']==records[0]['screenshot']
  check.call('响应丢失后重复保存成功且不重复写入',"#{review}.querySelectorAll('.comment').length===1")
  ui_click.call('[data-action=edit]')
  c.evaluate("#{review}.querySelector('#note-input').select()")
  c.call('Input.insertText',text:'按钮文案需要更明确。')
  ui_click.call('[data-action=save]')
  c.wait_for("!#{review}.querySelector('#note-input') && #{review}.querySelector('.comment p')?.textContent==='按钮文案需要更明确。'")
  ui_click.call('[data-action=list]')
  click.call('#disabled');check.call('禁用按钮也可选中评论',"#{review}.querySelector('.note strong').textContent==='禁用按钮'")
  ui_click.call('[data-action=cancel]')
  click.call('#link');check.call('链接评论不会跳转',"location.pathname==='/unregistered.html' && !!#{review}.querySelector('#note-input')")
  ui_click.call('[data-action=cancel]')
  ui_click.call('[data-mode=area]')
  drag.call(150,480,650,560)
  check.call('空白与跨元素区域可框选',"#{review}.querySelector('.note small').textContent==='区域评论' && parseInt(#{review}.querySelector('#outline').style.width)>=490")
  ui_click.call('[data-action=cancel]')
  ui_click.call('[data-mode=text]')
  points=c.evaluate("(()=>{const n=document.querySelector('#words').firstChild;const a=document.createRange(),z=document.createRange();a.setStart(n,0);a.setEnd(n,1);z.setStart(n,6);z.setEnd(n,7);const x=a.getBoundingClientRect(),y=z.getBoundingClientRect();return [x.x+1,x.y+x.height/2,y.right-1,y.y+y.height/2]})()")
  drag.call(*points)
  check.call('拖选文本保留准确引用',"#{review}.querySelector('.note blockquote')?.textContent.includes('准确选中')")
  b.screenshot(File.join(out,'02-text-selection.png'))
  ui_click.call('[data-action=cancel]')
  points=c.evaluate("(()=>{const r=document.querySelector('#field').getBoundingClientRect();return [r.x+13,r.y+r.height/2,r.x+85,r.y+r.height/2]})()")
  drag.call(*points)
  check.call('输入字段可整体选中且不修改内容',review+".querySelector('.note small')?.textContent==='元素评论' && document.querySelector('#field').value==='原来的输入'")
  c.call('Input.dispatchKeyEvent',type:'keyDown',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8)
  c.call('Input.dispatchKeyEvent',type:'keyUp',key:'Backspace',code:'Backspace',windowsVirtualKeyCode:8)
  check.call('原页面键盘编辑被拦截',"document.querySelector('#field').value==='原来的输入' && !counts.keydown")
  ui_click.call('[data-action=cancel]');ui_click.call('[data-mode=element]')
  click.call('#curve')
  check.call('SVG 连线可以直接点选',"!!"+review+".querySelector('#note-input') && "+review+".querySelector('#outline').getBoundingClientRect().width>400")
  c.step({'action'=>'key','key'=>'Escape'})
  check.call('Esc 先取消选区，仍在评论模式',"document.documentElement.hasAttribute('data-prototype-review-active') && !#{review}.querySelector('#note-input')")
  c.step({'action'=>'key','key'=>'Escape'})
  click.call('#original');check.call('退出评论后恢复原交互',"activated===1")
  navigate.call('index.html')
  click.call('#open-dialog')
  ui_click.call('[data-action=toggle]')
  click.call('#dialog-action')
  check.call('评论弹窗按钮不会触发动作或关闭弹窗',"!document.querySelector('#fixture-dialog').hidden && dialogActions===0")
  note.call('合成弹窗截图。');ui_click.call('[data-action=save]')
  c.wait_for("!#{review}.querySelector('#note-input')",30)
  check.call('合成弹窗现场截图保存成功',"!#{review}.querySelector('.error')")
  ui_click.call('[data-action=list]');ui_click.call('[data-action=toggle]')
  click.call('#dialog-action')
  check.call('退出后弹窗动作恢复可用',"dialogActions===1")
  click.call('#close-dialog')
  ui_click.call('[data-action=toggle]');ui_click.call('[data-mode=area]')
  c.evaluate('window.originalTransform=document.querySelector("#fixture-world").style.transform')
  drag.call(110,150,420,240)
  check.call('框选不会拖动合成画布',"document.querySelector('#fixture-world').style.transform===originalTransform")
  note.call('合成区域评论。');ui_click.call('[data-action=save]')
  c.wait_for("!#{review}.querySelector('#note-input')",30)
  check.call('合成区域评论保存成功',"!#{review}.querySelector('.error')")
  saved=JSON.parse(File.read(File.join(scratch,'data','comments.json'))).last
  check.call('截图保留 isolation 负层级图像',<<~JS)
    (async()=>{const image=new Image();image.src=#{JSON.generate(saved['screenshot'])};await image.decode();const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);const r=document.querySelector('.photo').getBoundingClientRect();const pixels=ctx.getImageData(r.x+6,r.y+6,Math.max(1,r.width-12),Math.max(1,r.height-12)).data;const colors=new Set();for(let i=0;i<pixels.length;i+=4)colors.add([pixels[i]>>4,pixels[i+1]>>4,pixels[i+2]>>4].join(','));return colors.size>100;})()
  JS
  ui_click.call('[data-action=list]');ui_click.call('[data-mode=element]')
  click.call('#fixture-title')
  c.evaluate("window.beforeOutline=#{review}.querySelector('#outline').getBoundingClientRect().x;document.querySelector('#fixture-world').style.transform+=' translateX(40px)'")
  c.wait_for("#{review}.querySelector('#outline').getBoundingClientRect().x>beforeOutline+20")
  check.call('锚点跟随元素变换，无需页面适配',"#{review}.querySelector('#outline').getBoundingClientRect().x>beforeOutline+20")
  navigate.call('unregistered.html')
  ui_click.call('[data-action=list]')
  check.call('跨页返回可读取已保存的评论',"#{review}.querySelector('.comment p')?.textContent==='按钮文案需要更明确。'")
  ui_click.call('[data-action=status]')
  c.wait_for("#{review}.querySelector('.comment-head span')?.textContent==='已解决'")
  check.call('评论状态可持久化更新',"#{review}.querySelector('.comment-head span').textContent==='已解决'")
  ui_click.call('[data-action=status]')
  c.wait_for("#{review}.querySelector('.comment-head span')?.textContent==='待处理'")
  check.call('已解决评论可重新打开',"#{review}.querySelector('.comment-head span').textContent==='待处理'")
  navigate.call('text.html')
  ui_click.call('[data-action=toggle]');ui_click.call('[data-mode=text]')
  points=c.evaluate("(()=>{const n=document.querySelector('#text-target').firstChild;const a=document.createRange(),z=document.createRange();a.setStart(n,0);a.setEnd(n,1);z.setStart(n,6);z.setEnd(n,7);const x=a.getBoundingClientRect(),y=z.getBoundingClientRect();return [x.x+1,x.y+x.height/2,y.right-1,y.y+y.height/2]})()")
  drag.call(*points);note.call('合成文字评论。');ui_click.call('[data-action=save]')
  c.wait_for("!#{review}.querySelector('#note-input')",30)
  check.call('文字标注可独立持久化',"#{review}.querySelector('.comment p')?.textContent==='合成文字评论。'")
  c.call('Page.navigate',url:'file://'+File.join(site,'index.html'))
  c.wait_for("!!window.PrototypeReview && !!document.querySelector('#fixture-world')")
  ui_click.call('[data-action=toggle]');click.call('button')
  note.call('离线评论验证');ui_click.call('[data-action=save]')
  c.wait_for("#{review}.querySelector('.comment p')?.textContent==='离线评论验证'")
  check.call('直接打开 HTML 可保存选区评论，并明确不附截图',"JSON.parse(localStorage.getItem('prototype.review.v1'))[0].snapshotNote==='离线文件评论，未附截图' && #{review}.querySelector('[data-action=snapshot]').textContent==='未附截图'")
  c.call('Page.reload');c.wait_for("!!window.PrototypeReview && !!#{review}.querySelector('[data-action=toggle]')")
  ui_click.call('[data-action=list]')
  check.call('离线评论刷新后仍保留',"#{review}.querySelector('.comment p')?.textContent==='离线评论验证'")
  exceptions=c.events.select{|e|e['method']=='Runtime.exceptionThrown'}
  raise JSON.generate(exceptions) unless exceptions.empty?
  File.write(File.join(out,'results.json'),JSON.pretty_generate({checks:checks,runtimeExceptions:exceptions,commentCount:JSON.parse(File.read(File.join(scratch,'data','comments.json'))).length,screenshotBytes:File.size(File.join(scratch,'data','screenshots',records[0]['id']+'.png'))}))
  puts "#{checks.length} checks passed"
ensure
  b.close if b
  Process.kill('TERM',pid) rescue nil
  Process.wait(pid) rescue nil
  FileUtils.remove_entry(scratch)
end
