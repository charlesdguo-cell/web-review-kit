require_relative '../support/browser'
require_relative '../support/fixture_site'

root = File.expand_path('../..', __dir__)
scratch = Dir.mktmpdir('shared-review-')
data = File.join(scratch, 'data')
FileUtils.mkdir_p(data)
site = File.join(scratch, 'site')
ReviewFixtureSite.create(site, root)
ReviewFixtureSite.seed_reviews(data)
manifest = File.join(data, 'comments.json')
initial_records = File.file?(manifest) ? JSON.parse(File.read(manifest)) : []
# The list defaults to this page; other pages now have their own review records.
initial_count = initial_records.count { |comment| ['/', '/index.html'].include?(comment.dig('page', 'path')) }
socket = TCPServer.new('127.0.0.1', 0); port = socket.addr[1]; socket.close
prefix = '/team/review/'
base = "http://127.0.0.1:#{port}#{prefix}"
pid = Process.spawn('python3', File.join(root, 'runtime/server.py'), '--root', site, '--data', data,
  '--port', port.to_s, '--base-path', prefix, '--public-origin', 'https://reviews.example.test', out: File.join(scratch, 'server.log'), err: [:child, :out])
browsers = []; checks = []
review = "document.querySelector('#prototype-review').shadowRoot"
check = lambda { |name, result| raise name unless result; checks << name; puts "PASS #{name}" }
ui = lambda { |c, selector| c.evaluate("#{review}.querySelector(#{JSON.generate(selector)}).click()") }
begin
  $stdout.sync = true
  Timeout.timeout(10) do
    loop do
      begin; break if Net::HTTP.get(URI(base + '__review/health')).include?('prototype-review'); rescue Errno::ECONNREFUSED; end
      sleep 0.1
    end
  end
  2.times do
    browser = PrototypeBrowser.new; browsers << browser
    c = browser.cdp
    c.call('Emulation.setDeviceMetricsOverride', width: 1362, height: 895, deviceScaleFactor: 1, mobile: false)
    c.call('Page.navigate', url: base + 'index.html')
    c.wait_for("!!document.querySelector('#fixture-world') && !!#{review}.querySelector('[data-action=list]')")
    ui.call(c, '[data-action=list]')
    c.wait_for("#{review}.querySelectorAll('.comment').length===#{initial_count}")
  end
  a, b = browsers.map(&:cdp)
  check.call('已有首页评论在部署前缀下全部显示', a.evaluate("#{review}.querySelectorAll('.comment').length===#{initial_count} && #{review}.querySelector('.comments small').textContent==='团队评审'"))
  check.call('已有截图均能通过部署路径读取', a.evaluate("(async()=>{const d=await(await fetch(#{JSON.generate(base + '__review/comments')})).json();return (await Promise.all(d.comments.map(async c=>{const r=await fetch(c.screenshot);return r.ok && (await r.blob()).size>1000}))).every(Boolean)})()"))
  ui.call(a, '[data-action=list]'); ui.call(a, '[data-action=toggle]')
  a.step({'action'=>'click', 'selector'=>'#fixture-link'})
  check.call('部署路径下评论导航链接不会触发跳转', a.evaluate("location.pathname.endsWith('/index.html') && !!#{review}.querySelector('#note-input')"))
  a.evaluate("#{review}.querySelector('#note-input').focus()")
  a.call('Input.insertText', text: '共享评审临时验证，不进入正式数据')
  a.evaluate(<<~JS)
    (()=>{const canvas=document.createElement('canvas');canvas.width=2;canvas.height=2;
    const bytes=Uint8Array.from(atob(canvas.toDataURL().split(',')[1]),x=>x.charCodeAt(0)),data=new DataTransfer();
    data.items.add(new File([bytes],'共享附图.png',{type:'image/png'}));
    #{review}.querySelector('#note-input').dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,composed:true,cancelable:true}));})()
  JS
  a.wait_for("#{review}.querySelectorAll('.attachment-drafts img').length===1 && !#{review}.querySelector('[data-action=save]').disabled")
  ui.call(a, '[data-action=save]')
  a.wait_for("#{review}.querySelectorAll('.comment').length===#{initial_count + 1} && !#{review}.querySelector('#note-input')", 30)
  b.wait_for("#{review}.querySelectorAll('.comment').length===#{initial_count + 1}", 22)
  check.call('另一位评审者自动收到新评论', true)
  saved = JSON.parse(File.read(File.join(data, 'comments.json'))).last
  b.wait_for("#{review}.querySelector('#comment-#{saved['id']} .attachment img')?.naturalWidth===2")
  check.call('另一位评审者可读取部署前缀下的评论附图', b.evaluate("#{review}.querySelector('#comment-#{saved['id']} .attachment img').src.includes(#{JSON.generate(prefix + '__review/attachments/')})"))
  ui.call(a, "[data-action=edit][data-id='#{saved['id']}']")
  ui.call(b, "[data-action=status][data-id='#{saved['id']}']")
  b.wait_for("#{review}.querySelector('#comment-#{saved['id']} .comment-head span').textContent==='已解决'")
  ui.call(a, '[data-action=refresh]')
  a.wait_for("#{review}.querySelector('#comment-#{saved['id']} .comment-head span').textContent==='已解决'")
  a.evaluate("const field=#{review}.querySelector('#note-input');field.focus();field.select()")
  a.call('Input.insertText', text: '旧编辑窗口不能覆盖同事的状态更新')
  ui.call(a, '[data-action=save]')
  a.wait_for("#{review}.querySelector('.error')?.textContent.includes('已更新')")
  check.call('自动刷新后旧编辑窗口仍受冲突保护且保留输入', a.evaluate("#{review}.querySelector('#note-input').value==='旧编辑窗口不能覆盖同事的状态更新'"))
  current = JSON.parse(File.read(File.join(data, 'comments.json'))).last
  check.call('冲突未覆盖已保存内容和截图', current['status'] == 'resolved' && current['text'] == saved['text'] && File.size(File.join(data, 'screenshots', saved['id'] + '.png')) > 1000)
  a.call('Page.navigate', url: base)
  a.wait_for("!!#{review}.querySelector('[data-action=list]')")
  ui.call(a, '[data-action=list]'); a.wait_for("#{review}.querySelectorAll('.comment').length===#{initial_count + 1}")
  check.call('目录入口与 index.html 共享相同评论', true)
  output = File.join(root, 'artifacts/validation-review/deployment'); FileUtils.mkdir_p(output)
  browsers.first.screenshot(File.join(output, 'shared-comments.png'))
  check.call('浏览器无运行异常', browsers.all? { |browser| browser.cdp.events.none? { |e| e['method'] == 'Runtime.exceptionThrown' } })
  File.write(File.join(output, 'shared-results.json'), JSON.pretty_generate({checks: checks, temporaryDataOnly: true}))
ensure
  browsers.each(&:close)
  Process.kill('TERM', pid) rescue nil
  Process.wait(pid) rescue nil
  FileUtils.remove_entry(scratch)
end
