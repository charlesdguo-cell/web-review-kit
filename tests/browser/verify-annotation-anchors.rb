require_relative '../support/browser'

# Only temporary synthetic data owned by run_browser_check is read or changed.
# No retained consumer data, account, task or worker is involved.
root = File.expand_path('../..', __dir__)
out = File.join(root, 'artifacts/validation-annotation-anchors')
FileUtils.mkdir_p(out)
fixture = ENV.fetch('ANNOTATIONS_FIXTURE')
base = ENV.fetch('ANNOTATIONS_TEST_URL')
ui = "document.querySelector('#prototype-review').shadowRoot"
b = PrototypeBrowser.new
c = b.cdp
checks = []
check = lambda { |name, expression| raise name unless c.evaluate(expression); checks << name; puts "PASS #{name}" }
ready = lambda { c.wait_for("window.PrototypeReview&&#{ui}.querySelector('link')?.sheet&&#{ui}.querySelector('[data-action=annotations]')") }
activate = lambda do |id|
  c.evaluate("#{ui}.querySelector('.annotation-card[data-id=\"#{id}\"] [data-action=annotation-open]').click()")
  c.wait_for("!!#{ui}.querySelector('.annotation-card[data-id=\"#{id}\"] #annotation-followup')")
  c.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
end
get = "fetch('/__review/annotations').then(r=>r.json()).then(d=>d.annotations)"
begin
  $stdout.sync = true
  c.call('Emulation.setDeviceMetricsOverride', width:1440, height:1000, deviceScaleFactor:1, mobile:false)
  c.call('Page.navigate', url:base)
  ready.call
  c.evaluate(<<~JS)
    (async()=>{window.anchorFixtures=[];
      const rows=[['stable','#stable'],['section','section.reading'],['leading','section.leading-context'],['deleted','#deleted'],['replacement','section.replacement'],['position','.positioned > p:nth-of-type(1)'],['exact','#exact']];
      for(const [name,selector] of rows){const el=document.querySelector(selector),text=el.textContent,exact=name==='section'?'Original section sentence.':name==='leading'?'Original leading quote.':text,start=text.indexOf(exact),end=start+exact.length,r=el.getBoundingClientRect();
        const record={id:'annotation-'+name,text:'Synthetic retained discussion '+name,status:'open',page:{path:'/',title:'Synthetic anchors'},attachments:[],
          screenshotData:'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLttAAAAABJRU5ErkJggg==',
          anchor:{kind:'text',selector,tag:el.tagName,label:text.slice(0,100),fingerprint:text.slice(0,100),selectedText:exact,html:el.outerHTML,
            rect:{x:r.x,y:r.y,width:r.width,height:r.height},documentRect:{x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height},
            relative:{x:0,y:0,width:1,height:1},ancestors:[{selector,tag:el.tagName,label:text.slice(0,100),attributes:{},transform:'none'}],
            textRange:{start,end,exact,prefix:text.slice(Math.max(0,start-40),start),suffix:text.slice(end,end+40)}}};
        const response=await fetch('/__review/annotations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({annotation:record,autoReply:false})});
        if(!response.ok)throw Error(await response.text());window.anchorFixtures.push((await response.json()).annotation);
      }
    })()
  JS
  original = c.evaluate(get)
  c.evaluate("#{ui}.querySelector('[data-action=annotations]').click()") unless c.evaluate("!!#{ui}.querySelector('.annotation-sidebar')")
  c.wait_for("#{ui}.querySelectorAll('.annotation-card').length===7")
  c.evaluate(<<~JS)
    document.querySelector('#stable').textContent='Revised statement keeps the discussion attached to its original paragraph.';
    document.querySelector('section.reading p:nth-of-type(2)').textContent='Revised section sentence.';
    document.querySelector('section.leading-context h2').textContent='Revised leading title.';
    document.querySelector('#deleted').remove();
    document.querySelector('section.replacement').outerHTML='<section class="replacement">A completely unrelated replacement occupies the old location.</section>';
    document.querySelector('.positioned p:first-child').remove();
    window.dispatchEvent(new Event('resize'));
  JS
  activate.call('annotation-stable')
  check.call('Rewritten stable identity retains a distinct paragraph marker', "!!#{ui}.querySelector('.annotation-marker-block[data-id=annotation-stable]')")
  check.call('Paragraph fallback never paints rewritten text as the original exact quote', "!#{ui}.querySelector('.annotation-highlight[data-id=annotation-stable]')&&#{ui}.querySelector('.annotation-card[data-id=annotation-stable] .annotation-quote').textContent==='Stable original quotation for an explicit identity.'")
  check.call('Active rewritten-paragraph card stays beside its retained container', "Math.abs(#{ui}.querySelector('.annotation-card[data-id=annotation-stable]').getBoundingClientRect().top-document.querySelector('#stable').getBoundingClientRect().top)<32")
  activate.call('annotation-section')
  check.call('Unique section with retained surrounding text has a paragraph marker', "!!#{ui}.querySelector('.annotation-marker-block[data-id=annotation-section]')&&!#{ui}.querySelector('.annotation-highlight[data-id=annotation-section]')")
  check.call('Retained section card keeps document position instead of moving behind every exact quote', "Math.abs(#{ui}.querySelector('.annotation-card[data-id=annotation-section]').getBoundingClientRect().top-document.querySelector('section.reading').getBoundingClientRect().top)<32")
  activate.call('annotation-leading')
  check.call('Whitespace-only prefix does not disqualify a section confirmed by its unique preserved suffix', "!!#{ui}.querySelector('.annotation-marker-block[data-id=annotation-leading]')&&!#{ui}.querySelector('.annotation-highlight[data-id=annotation-leading]')")
  c.evaluate("document.querySelector('#stable').scrollIntoView({block:'center'});window.dispatchEvent(new Event('resize'))")
  c.evaluate("#{ui}.querySelector('.annotation-marker-block[data-id=annotation-stable]').click()")
  check.call('Paragraph marker opens its original retained discussion and describes the fallback accessibly', "!!#{ui}.querySelector('.annotation-card[data-id=annotation-stable] #annotation-followup')&&#{ui}.querySelector('.annotation-marker-block[data-id=annotation-stable]').getAttribute('aria-label').includes('原文已变化')")
  c.evaluate('scrollTo(0,0);window.dispatchEvent(new Event("resize"))')
  check.call('Deleted, unrelated and positional replacements receive no fabricated markers or highlights', "['deleted','replacement','position'].every(id=>!#{ui}.querySelector('.annotation-marker[data-id=annotation-'+id+'],.annotation-highlight[data-id=annotation-'+id+']'))")
  check.call('Unchanged exact quotation retains its text highlight', "!!#{ui}.querySelector('.annotation-highlight[data-id=annotation-exact]')")
  activate.call('annotation-deleted')
  check.call('Deleted original still has an accessible card with its saved quote and stale notice', "#{ui}.querySelector('#annotation-quote').textContent==='Deleted original paragraph has a preserved discussion.'&&#{ui}.querySelector('#annotation-state').textContent.includes('原文已变化')")
  # A fixture-owned public conversation snapshot exercises progress/error rendering;
  # it does not create a task, start the fake protocol executable, or modify a worker.
  thread_dir = File.join(fixture, 'data/annotation-threads')
  FileUtils.mkdir_p(thread_dir)
  snapshot = File.join(thread_dir, 'annotation-stable.json')
  File.write(snapshot, JSON.generate(id:'annotation-stable',status:'running',canChat:true,hasAgent:true,messages:[]))
  activate.call('annotation-stable')
  c.wait_for("#{ui}.querySelector('#annotation-state').textContent.includes('Agent 回复中')")
  check.call('Running Agent state remains visible alongside the changed-original notice', "#{ui}.querySelector('#annotation-state').textContent.includes('原文已变化')")
  File.write(snapshot, JSON.generate(id:'annotation-stable',status:'failed',canChat:true,hasAgent:true,error:'Synthetic retryable failure',messages:[]))
  c.wait_for("#{ui}.querySelector('#annotation-state').textContent.includes('Synthetic retryable failure')")
  check.call('Agent failure remains visible alongside the changed-original notice', "#{ui}.querySelector('#annotation-state').textContent.includes('原文已变化')")
  FileUtils.rm_f(snapshot)
  c.evaluate("document.querySelectorAll('#stable,section.reading,section.leading-context,section.replacement,.positioned,#exact').forEach(el=>el.remove());scrollTo(0,0);window.dispatchEvent(new Event('resize'))")
  activate.call('annotation-deleted')
  c.evaluate('scrollTo(0,0)')
  c.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
  geometry = "({height:document.documentElement.scrollHeight,cards:[...#{ui}.querySelectorAll('.annotation-card')].map(card=>({id:card.dataset.id,documentTop:card.getBoundingClientRect().top+scrollY}))})"
  c.evaluate("window.orphanGeometry=#{geometry}")
  [220,550,900,1250].each do |offset|
    c.evaluate("scrollTo(0,#{offset})")
    c.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
    check.call("All-missing cards retain stable document coordinates and scroll height at #{offset}px", "(()=>{const now=#{geometry};return Math.abs(now.height-window.orphanGeometry.height)<=2&&now.cards.every(card=>Math.abs(card.documentTop-window.orphanGeometry.cards.find(before=>before.id===card.id).documentTop)<=2)})()")
  end
  check.call('Navigation remains available when every original container is gone', "!#{ui}.querySelector('[data-action=annotation-next]').disabled||!#{ui}.querySelector('[data-action=annotation-prev]').disabled")
  c.evaluate("#{ui}.querySelector('[data-action=annotation-next]').click()")
  check.call('Navigation reaches a visible retained discussion when the original container is gone', "(()=>{const card=#{ui}.querySelector('.annotation-card[data-active=true]'),r=card?.getBoundingClientRect();return card&&card.dataset.id!=='annotation-deleted'&&r.bottom>60&&r.top<innerHeight-60})()")
  after = c.evaluate(get)
  raise 'Anchor display fallback changed persisted annotation records' unless original == after
  checks << 'All annotation fields, original quotes, evidence and timestamps remain byte-equivalent in API records'
  puts "PASS #{checks.last}"
  rpc = File.join(fixture, 'rpc.jsonl')
  raise 'Anchor display checks dispatched an Agent task' if File.exist?(rpc) && File.readlines(rpc).any? { |line| JSON.parse(line)['method']=='turn/start' }
  errors = c.events.select { |event| event['method']=='Runtime.exceptionThrown' }
  raise 'Browser runtime exception' unless errors.empty?
  b.screenshot(File.join(out,'retained-anchors.png'))
  File.write(File.join(out,'result.json'), JSON.pretty_generate(checks:checks,runtimeErrors:errors,agentTurns:0))
  %w[failure.png failure-state.json failure.txt].each { |name| FileUtils.rm_f(File.join(out,name)) }
  puts JSON.generate(ok:true,checks:checks.length,agentTurns:0)
rescue StandardError => error
  File.write(File.join(out,'failure.txt'),"#{error.class}: #{error.message}\n")
  File.write(File.join(out,'failure-state.json'),JSON.pretty_generate(c.evaluate("({scrollY,body:document.body.innerHTML,ui:#{ui}.innerHTML})"))) rescue nil
  b.screenshot(File.join(out,'failure.png')) rescue nil
  raise
ensure
  b.close
end
