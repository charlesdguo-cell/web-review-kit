require_relative '../support/browser'

root=File.expand_path('../..',__dir__)
out=File.join(root,'artifacts/validation-review-startup')
FileUtils.mkdir_p(out)
base=ENV.fetch('REVIEW_STARTUP_URL')
fixture=ENV.fetch('REVIEW_STARTUP_FIXTURE')
ui="document.querySelector('#prototype-review').shadowRoot"
checks=[]
b=PrototypeBrowser.new
c=b.cdp
$stdout.sync=true
check=lambda do |name,expression|
  unless c.evaluate(expression)
    details=c.evaluate("({path:location.pathname,host:document.querySelector('#prototype-review')?.getAttribute('style'),sheet:!!#{ui}.querySelector('link').sheet,frames:startupFrames})")
    raise "#{name}: #{details.to_json}"
  end
  checks<<name;puts "PASS #{name}"
end
ready=lambda{|path|c.wait_for("location.pathname===#{path.to_json}&&window.PrototypeReview&&#{ui}.querySelector('link').sheet&&getComputedStyle(#{ui}.querySelector('#toolbar')).visibility==='visible'")}
click=lambda do |expression|
  xy=c.evaluate("(()=>{const r=(#{expression}).getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
  c.call('Input.dispatchMouseEvent',type:'mousePressed',x:xy['x'],y:xy['y'],button:'left',clickCount:1)
  c.call('Input.dispatchMouseEvent',type:'mouseReleased',x:xy['x'],y:xy['y'],button:'left',clickCount:1)
end
begin
  c.call('Emulation.setDeviceMetricsOverride',width:1280,height:900,deviceScaleFactor:1,mobile:false)
  c.call('Network.enable')
  c.call('Page.addScriptToEvaluateOnNewDocument',source:<<~JS)
    window.startupFrames=[];window.startupDocument=crypto.randomUUID();
    function recordStartupFrame(){
      const host=document.querySelector('#prototype-review'),toolbar=host?.shadowRoot?.querySelector('#toolbar');
      if(toolbar?.textContent){const style=getComputedStyle(toolbar);window.startupFrames.push({visibility:style.visibility,position:style.position});}
      requestAnimationFrame(recordStartupFrame);
    }
    requestAnimationFrame(recordStartupFrame);
  JS
  c.call('Page.navigate',url:base+'delayed/index.html')
  c.wait_for("window.PrototypeReview&&#{ui}.querySelector('[data-action=toggle]')&&startupFrames.length>2")
  check.call('Slow stylesheet keeps the populated review UI hidden',"!#{ui}.querySelector('link').sheet&&startupFrames.every(frame=>frame.visibility==='hidden')")
  click.call("document.querySelector('#ordinary')")
  check.call('Page remains interactive while review styles are pending','pageActions===1')
  c.evaluate("#{ui}.querySelector('[data-action=toggle]').focus()")
  check.call('Hidden review controls cannot receive keyboard focus',"document.activeElement!==document.querySelector('#prototype-review')")
  b.screenshot(File.join(out,'stylesheet-pending.png'))
  File.write(File.join(fixture,'release-style'),'ready')
  ready.call('/delayed/index.html')
  check.call('Loaded stylesheet reveals the toolbar at its fixed position',"(()=>{const bar=#{ui}.querySelector('#toolbar'),rect=bar.getBoundingClientRect();return getComputedStyle(bar).position==='fixed'&&rect.top>innerHeight/2&&Math.abs(rect.left+rect.width/2-innerWidth/2)<2;})()")
  check.call('No animation frame exposed an unstyled toolbar',"startupFrames.every(frame=>frame.visibility==='hidden'||frame.position==='fixed')")
  b.screenshot(File.join(out,'stylesheet-ready.png'))
  click.call("#{ui}.querySelector('[data-action=toggle]')")
  c.evaluate('window.pageActions=0;window.capturedClicks=0')
  click.call("document.querySelector('#ordinary')")
  check.call('Review still intercepts clicks before application capture listeners',"pageActions===0&&capturedClicks===0&&!!#{ui}.querySelector('#note-input')")
  c.evaluate("#{ui}.querySelector('[data-action=cancel]').click();#{ui}.querySelector('[data-action=toggle]').click()")
  c.evaluate("(()=>{const range=document.createRange();range.selectNodeContents(document.querySelector('#quote'));getSelection().removeAllRanges();getSelection().addRange(range);document.dispatchEvent(new Event('selectionchange'));})()")
  c.wait_for("#{ui}.querySelector('[data-action=annotation-create]')")
  check.call('Independent text annotation control remains available',"getComputedStyle(#{ui}.querySelector('[data-action=annotation-create]')).visibility==='visible'")
  click.call("#{ui}.querySelector('[data-action=annotation-create]')")
  c.wait_for("#{ui}.querySelector('#annotation-input')")
  c.evaluate("#{ui}.querySelector('#annotation-input').focus()")
  c.call('Input.insertText',text:'Keep this synthetic draft and its focus.')
  c.evaluate("#{ui}.querySelector('#annotation-input').setSelectionRange(5,9)")
  previous=c.evaluate('startupDocument')
  File.delete(File.join(fixture,'release-style'))
  c.call('Page.reload')
  c.wait_for("startupDocument!==#{previous.to_json}&&window.PrototypeReview&&#{ui}.querySelector('[data-action=toggle]')")
  # Restoring the saved focus must wait for real CSS readiness, even past the
  # former one-second view-restoration timeout.
  c.evaluate('new Promise(resolve=>setTimeout(resolve,1300))')
  check.call('Pending styles do not reserve space for a restored annotation sidebar',"getComputedStyle(document.body).paddingRight==='0px'&&document.body.getAttribute('style')===null")
  File.write(File.join(fixture,'release-style'),'ready')
  ready.call('/delayed/index.html')
  c.wait_for("#{ui}.activeElement?.id==='annotation-input'",3)
  check.call('Slow reload preserves the annotation draft, focus and text selection',"(()=>{const input=#{ui}.querySelector('#annotation-input');return input.value==='Keep this synthetic draft and its focus.'&&input.selectionStart===5&&input.selectionEnd===9;})()")
  previous=c.evaluate('startupDocument')
  File.write(File.join(fixture,'fail-style'),'fail')
  c.call('Page.reload')
  c.wait_for("startupDocument!==#{previous.to_json}&&document.readyState==='complete'&&window.PrototypeReview&&startupFrames.length>2")
  c.evaluate('new Promise(resolve=>setTimeout(resolve,1700))')
  check.call('Failed styles leave a saved open sidebar hidden without changing the page layout',"startupFrames.every(frame=>frame.visibility==='hidden')&&getComputedStyle(document.body).paddingRight==='0px'&&document.body.getAttribute('style')===null")
  check.call('Failed styles and polling preserve the stored annotation view and input selection',"(()=>{const saved=JSON.parse(sessionStorage.getItem('prototype.review.annotationView.'+encodeURIComponent('/delayed/')));return saved.open&&saved.focus?.id==='annotation-input'&&saved.focus.start===5&&saved.focus.end===9;})()")
  click.call("document.querySelector('#ordinary')")
  check.call('A hidden saved sidebar leaves ordinary page actions usable','pageActions===1')
  previous=c.evaluate('startupDocument')
  File.delete(File.join(fixture,'fail-style'))
  c.call('Page.reload')
  c.wait_for("startupDocument!==#{previous.to_json}&&window.PrototypeReview")
  ready.call('/delayed/index.html')
  c.wait_for("#{ui}.activeElement?.id==='annotation-input'",3)
  check.call('Reload after a CSS failure recovers the saved annotation draft and focus',"#{ui}.querySelector('#annotation-input').value==='Keep this synthetic draft and its focus.'")
  previous=c.evaluate('startupDocument')
  File.delete(File.join(fixture,'release-style'))
  c.call('Page.reload')
  c.wait_for("startupDocument!==#{previous.to_json}&&window.PrototypeReview")
  c.step('action'=>'fill','selector'=>'#page-input','text'=>'Editing during CSS loading')
  File.write(File.join(fixture,'release-style'),'ready')
  ready.call('/delayed/index.html')
  c.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
  check.call('Restoring review does not steal focus from a page input used during loading',"document.activeElement.id==='page-input'&&document.querySelector('#page-input').value==='Editing during CSS loading'")

  c.call('Page.navigate',url:base+'missing/index.html')
  c.wait_for("location.pathname==='/missing/index.html'&&document.readyState==='complete'&&window.PrototypeReview&&startupFrames.length>2")
  check.call('Failed stylesheet never exposes the unstyled review UI',"getComputedStyle(#{ui}.querySelector('#toolbar')).position==='static'&&startupFrames.every(frame=>frame.visibility==='hidden')")
  click.call("document.querySelector('#ordinary')")
  check.call('A stylesheet failure leaves page actions usable','pageActions===1')
  b.screenshot(File.join(out,'stylesheet-failed.png'))

  c.call('Page.navigate',url:base+'cached/first.html');ready.call('/cached/first.html')
  c.call('Page.navigate',url:base+'cached/second.html');ready.call('/cached/second.html')
  check.call('Cached stylesheet still reveals the correctly positioned toolbar',"getComputedStyle(#{ui}.querySelector('#toolbar')).position==='fixed'&&startupFrames.every(frame=>frame.visibility==='hidden'||frame.position==='fixed')")
  requests=JSON.parse(Net::HTTP.get(URI(base+'requests')))
  raise 'Expected one real CSS request followed by a cache hit' unless requests['/cached/review.css']==1
  checks << 'Second navigation uses the cached stylesheet without another request'
  puts "PASS #{checks.last}"
  errors=c.events.select{|event|event['method']=='Runtime.exceptionThrown'}
  raise errors.to_json unless errors.empty?
  File.write(File.join(out,'results.json'),JSON.pretty_generate(checks:checks,requests:requests,errors:errors))
  puts "PASS #{checks.length} review startup checks"
ensure
  b.close
end
