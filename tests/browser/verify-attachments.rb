require_relative '../support/browser'
require 'digest'
require_relative '../support/fixture_site'

root = File.expand_path('../..', __dir__)
scratch = Dir.mktmpdir('review-attachments-')
site = File.join(scratch, 'site')
ReviewFixtureSite.create(site, root)
File.write(File.join(site, 'paste.html'), <<~HTML)
  <!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>评论附图验证</title>
  <style>body{margin:40px;background:#10111b;color:#eee;font:18px sans-serif}button{padding:20px}</style></head>
  <body><button id="target">评审这个区块</button><script>window.pagePastes=0;window.addEventListener('paste',()=>pagePastes++,true)</script></body></html>
HTML
socket = TCPServer.new('127.0.0.1', 0); port = socket.addr[1]; socket.close
log = File.join(scratch, 'server.log')
pid = Process.spawn('python3', File.join(root, 'runtime/server.py'), '--root', site, '--data', File.join(scratch, 'data'), '--port', port.to_s, out: log, err: [:child, :out])
b = nil
out = File.join(root, 'artifacts/validation-review'); FileUtils.mkdir_p(out)
checks = []; $stdout.sync = true
begin
  Timeout.timeout(10) do
    loop do
      begin; break if Net::HTTP.get(URI("http://127.0.0.1:#{port}/__review/health")).include?('prototype-review'); rescue Errno::ECONNREFUSED; end
      sleep 0.1
    end
  end
  b = PrototypeBrowser.new; c = b.cdp
  c.call('Emulation.setDeviceMetricsOverride', width: 1440, height: 980, deviceScaleFactor: 1, mobile: false)
  review = "document.querySelector('#prototype-review').shadowRoot"
  check = lambda do |name, expression|
    raise name unless c.evaluate(expression)
    checks << name; puts "PASS #{name}"
  end
  click = lambda do |selector|
    # Resize can rebuild the editor; wait for layout before measuring the current button.
    point = c.evaluate("(async()=>{#{review}.querySelector(#{JSON.generate(selector)}).scrollIntoView({block:'nearest'});await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));const r=#{review}.querySelector(#{JSON.generate(selector)}).getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
    c.call('Input.dispatchMouseEvent', type: 'mousePressed', x: point['x'], y: point['y'], button: 'left', clickCount: 1)
    c.call('Input.dispatchMouseEvent', type: 'mouseReleased', x: point['x'], y: point['y'], button: 'left', clickCount: 1)
  end
  # Synthetic clipboard payloads exercise the real paste handler without touching the user's clipboard.
  paste = lambda do |count = 1, text = '', mime = 'image/png'|
    c.evaluate(<<~JS)
      (()=>{const canvas=document.createElement('canvas');canvas.width=160;canvas.height=90;
      const ctx=canvas.getContext('2d');ctx.fillStyle='#bcafff';ctx.fillRect(0,0,160,90);ctx.fillStyle='#161624';ctx.font='24px sans-serif';ctx.fillText('Reference',18,53);
      const bytes=Uint8Array.from(atob(canvas.toDataURL().split(',')[1]),x=>x.charCodeAt(0)),data=new DataTransfer();
      for(let i=0;i<#{count};i++)data.items.add(new File([bytes],'参考 '+i+'.png',{type:#{JSON.generate(mime)}}));
      if(#{JSON.generate(text)})data.setData('text/plain',#{JSON.generate(text)});
      const field=#{review}.querySelector('#note-input');field.focus();
      const event=new ClipboardEvent('paste',{clipboardData:data,bubbles:true,composed:true,cancelable:true});
      field.dispatchEvent(event);return event.defaultPrevented;})()
    JS
  end
  images = "#{review}.querySelectorAll('.attachment-drafts img')"
  records = lambda { JSON.parse(File.read(File.join(scratch, 'data/comments.json'))) }
  c.call('Page.navigate', url: "http://127.0.0.1:#{port}/paste.html")
  c.wait_for("!!window.PrototypeReview && !!#{review}.querySelector('[data-action=toggle]')")
  click.call('[data-action=toggle]'); c.step({'action' => 'click', 'selector' => '#target'})
  paste.call(2)
  c.wait_for("#{images}.length===2 && [...#{images}].every(i=>i.complete&&i.naturalWidth===160)")
  check.call('粘贴多图可预览且不触发原页面粘贴', 'pagePastes===0')
  b.screenshot(File.join(out, 'attachments-editor.png'))
  targets = c.call('Target.getTargets')['targetInfos'].map { |t| t['targetId'] }
  click.call('[data-action=preview-attachment]')
  new_target = nil
  Timeout.timeout(5) do
    loop do
      new_target = c.call('Target.getTargets')['targetInfos'].find { |t| !targets.include?(t['targetId']) && t['type'] == 'page' }
      break if new_target
      sleep 0.1
    end
  end
  c.call('Target.closeTarget', targetId: new_target['targetId'])
  checks << '点击附图打开独立预览'; puts "PASS #{checks.last}"
  click.call('[data-action=save]')
  c.wait_for("!#{review}.querySelector('#note-input') && #{review}.querySelectorAll('.comment img').length===2", 30)
  saved = records.call.first
  snapshot = Digest::SHA256.file(File.join(scratch, 'data/screenshots', saved['id'] + '.png')).hexdigest
  raise 'Image-only persistence failed' unless saved['text'] == '' && saved['attachments'].length == 2 && saved['attachments'].all? { |a| a['url'] && !a['dataUrl'] }
  checks << '纯图片评论保存成功，附图和原定位截图分别落盘'; puts "PASS #{checks.last}"
  c.call('Page.reload'); c.wait_for("!!window.PrototypeReview && !!#{review}.querySelector('[data-action=list]')")
  click.call('[data-action=list]'); c.wait_for("!!#{review}.querySelector('[data-action=edit]')"); click.call('[data-action=edit]')
  c.wait_for("#{images}.length===2 && [...#{images}].every(i=>i.naturalWidth===160)")
  click.call('[data-action=remove-attachment]'); click.call('[data-action=cancel]')
  click.call('[data-action=edit]')
  check.call('刷新读取附图，移除后取消不影响原评论', "#{images}.length===2")
  raise 'Plain text paste was prevented' if paste.call(0, '普通文本')
  paste.call(1, '新参考图说明')
  c.wait_for("#{images}.length===3")
  check.call('图文一起粘贴保留文字，纯文本粘贴保留浏览器默认行为', "#{review}.querySelector('#note-input').value==='新参考图说明'")
  c.evaluate(<<~JS)
    (()=>{const originalFetch=window.fetch;window.fetch=async(...args)=>{const response=await originalFetch(...args);
    if(args[1]?.method==='POST'){window.fetch=originalFetch;throw new TypeError('Failed to fetch');}return response;};})()
  JS
  click.call('[data-action=save]'); c.wait_for("#{review}.querySelector('.error')?.textContent.includes('内容已保留')")
  committed = records.call
  check.call('响应丢失保留文字与全部附图', "#{images}.length===3 && #{review}.querySelector('#note-input').value==='新参考图说明'")
  click.call('[data-action=save]'); c.wait_for("!#{review}.querySelector('#note-input')")
  raise 'Retry changed record' unless records.call == committed
  checks << '附图保存重试不重复写入或改变版本'; puts "PASS #{checks.last}"
  downloads = File.join(scratch, 'downloads'); FileUtils.mkdir_p(downloads)
  c.call('Browser.setDownloadBehavior', behavior: 'allow', downloadPath: downloads)
  click.call('[data-action=export]')
  exported = nil
  Timeout.timeout(10) do
    loop do
      exported = Dir.glob(File.join(downloads, '*.json')).first
      break if exported
      sleep 0.1
    end
  end
  data = JSON.parse(File.read(exported))
  raise 'Export incomplete' unless data['version'] == 2 && data['comments'].first['screenshotData'].start_with?('data:image/png;base64,') && data['comments'].first['attachments'].all? { |a| a['dataUrl'].start_with?('data:image/png;base64,') }
  checks << '导出包含可离线读取的全部附图及原截图'; puts "PASS #{checks.last}"
  click.call('[data-action=edit]'); paste.call(4)
  check.call('超过六张给出提示并保留已有附图', "#{images}.length===3 && #{review}.querySelector('.error').textContent.includes('最多')")
  paste.call(1, '', 'image/svg+xml')
  check.call('不支持的图片格式给出提示并保留草稿', "#{images}.length===3 && #{review}.querySelector('.error').textContent.includes('PNG')")
  paste.call(3); c.wait_for("#{images}.length===6")
  c.call('Emulation.setDeviceMetricsOverride', width: 390, height: 600, deviceScaleFactor: 1, mobile: true)
  c.evaluate("window.dispatchEvent(new Event('resize'))")
  c.evaluate("#{review}.querySelector('[data-action=save]').scrollIntoView({block:'nearest'})")
  check.call('小屏六张附图时保存按钮仍可滚动到可见区域', "(()=>{const e=#{review}.querySelector('#editor'),r=#{review}.querySelector('[data-action=save]').getBoundingClientRect();return e.scrollWidth<=e.clientWidth+1&&r.top>=0&&r.bottom<=innerHeight&&r.right<=innerWidth})()")
  b.screenshot(File.join(out, 'attachments-mobile.png'))
  c.call('Emulation.setDeviceMetricsOverride', width: 1440, height: 980, deviceScaleFactor: 1, mobile: false)
  6.times { click.call('[data-action=remove-attachment]') }
  click.call('[data-action=save]'); c.wait_for("!#{review}.querySelector('#note-input')")
  raise 'Removing images changed snapshot' unless records.call.first['attachments'] == [] && snapshot == Digest::SHA256.file(File.join(scratch, 'data/screenshots', saved['id'] + '.png')).hexdigest
  checks << '移除附图后保存，原定位截图保持不变'; puts "PASS #{checks.last}"
  c.call('Page.navigate', url: 'file://' + File.join(site, 'index.html'))
  c.wait_for("!!window.PrototypeReview && !!document.querySelector('#fixture-world')")
  click.call('[data-action=toggle]'); c.step({'action' => 'click', 'selector' => 'button'})
  paste.call; c.wait_for("#{images}.length===1")
  click.call('[data-action=save]'); c.wait_for("!#{review}.querySelector('#note-input')")
  c.call('Page.reload'); c.wait_for("!!window.PrototypeReview && !!#{review}.querySelector('[data-action=list]')")
  click.call('[data-action=list]')
  c.wait_for("#{review}.querySelector('.comment img')?.naturalWidth===160")
  check.call('离线入口也能粘贴图片并在刷新后保留', "JSON.parse(localStorage.getItem('prototype.review.v1'))[0].attachments[0].dataUrl.startsWith('data:image/png;base64,')")
  exceptions = c.events.select { |e| e['method'] == 'Runtime.exceptionThrown' }
  raise JSON.generate(exceptions) unless exceptions.empty?
  File.write(File.join(out, 'attachment-results.json'), JSON.pretty_generate({checks: checks, runtimeExceptions: exceptions}))
  puts "#{checks.length} attachment checks passed"
rescue
  b.screenshot(File.join(out, 'attachments-failure.png')) if b
  warn File.read(log)
  raise
ensure
  b.close if b
  Process.kill('TERM', pid) rescue nil
  Process.wait(pid) rescue nil
  FileUtils.remove_entry(scratch)
end
