# Read-only browser verification of the retained project. Never dispatches or updates comments.
require_relative '../support/browser'
root=File.expand_path(ENV.fetch('VALIDATION_PROJECT'));raise 'Wrong project' unless root=='/Users/charles/.local/share/web-review-kit-validation'
base='http://127.0.0.1:8791/';out=File.join(root,'artifacts/acceptance');b=PrototypeBrowser.new;c=b.cdp;checks=[];ui="document.querySelector('#prototype-review').shadowRoot"
check=lambda{|name,result|raise name unless result;checks<<name;puts 'PASS '+name}
click=lambda{|selector|c.evaluate("#{ui}.querySelector(#{selector.to_json}).click()")}
begin
 $stdout.sync=true
 c.call('Emulation.setDeviceMetricsOverride',width:1360,height:960,deviceScaleFactor:1,mobile:false)
 c.call('Page.navigate',url:base)
 c.wait_for("document.querySelector('#page-title')?.textContent==='Field collection'&&!!#{ui}.querySelector('[data-action=list]')")
 check.call('built page shows real worker title and supplement',c.evaluate("document.querySelector('#eyebrow').textContent==='Independent static project'"))
 click.call('[data-action=list]')
 c.wait_for("#{ui}.querySelectorAll('.comment').length===2")
 check.call('retained sample comments show changed and open',c.evaluate("[...#{ui}.querySelectorAll('.comment-head span')].map(e=>e.textContent).sort().join(',')==='待处理,待验收'"))
 c.wait_for("#{ui}.querySelector('.attachment img')?.naturalWidth===96")
 check.call('original attachment remains visible',true)
 b.screenshot(File.join(out,'retained-comments.png'))
 # Open only existing history. Pending #2 means the main codex button would dispatch; never click it here.
 c.wait_for("!!#{ui}.querySelector('[data-action=codex-details]')")
 click.call('[data-action=codex-details]')
 c.wait_for("#{ui}.querySelector('#codex-thread')?.textContent.includes('本次只解释')")
 check.call('real same-thread follow-up visible without dispatch',c.evaluate("#{ui}.querySelector('#codex-thread').textContent.includes('Field collection')"))
 b.screenshot(File.join(out,'retained-same-thread.png'))
 c.call('Page.navigate',url:base+'specimen.html')
 c.wait_for("document.querySelector('#sample-audio')?.readyState>=1")
 # A real trusted pointer gesture establishes browser activation before play().
 c.step({'action'=>'click','selector'=>'#sample-audio'})
 c.evaluate("document.querySelector('#sample-audio').play()")
 c.wait_for("document.querySelector('#sample-audio').currentTime>0")
 check.call('trusted pointer gesture starts actual synthetic audio playback',c.evaluate("document.querySelector('#sample-audio').duration===2"))
 b.screenshot(File.join(out,'detail-after.png'))
 c.call('Page.navigate',url:base)
 c.wait_for("document.querySelector('#page-title')?.textContent==='Field collection'")
 b.screenshot(File.join(out,'collection-after.png'))
 c.call('Emulation.setDeviceMetricsOverride',width:390,height:844,deviceScaleFactor:1,mobile:false)
 check.call('narrow page remains within viewport',c.evaluate("document.documentElement.scrollWidth<=innerWidth"))
 b.screenshot(File.join(out,'collection-narrow.png'))
 errors=c.events.select{|e|e['method']=='Runtime.exceptionThrown'}
 check.call('retained browser reports no runtime exception',errors.empty?)
 File.write(File.join(out,'retained-browser-results.json'),JSON.pretty_generate(checks:checks,readOnly:true))
rescue=>e
 b.screenshot(File.join(out,'retained-browser-failure.png')) rescue nil
 raise
ensure
 b.close
end
