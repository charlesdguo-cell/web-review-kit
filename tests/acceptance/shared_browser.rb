require_relative '../support/browser'
base=ENV.fetch('SHARED_ACCEPTANCE_URL');out=ENV.fetch('SHARED_ACCEPTANCE_OUT')
browsers=[];checks=[];ui="document.querySelector('#prototype-review').shadowRoot"
check=lambda{|name,result|raise name unless result;checks<<name;puts 'PASS '+name}
click=lambda{|c,sel|c.evaluate("#{ui}.querySelector(#{sel.to_json}).click()")}
begin
 $stdout.sync=true
 2.times do
  browser=PrototypeBrowser.new;browsers<<browser;c=browser.cdp
  c.call('Security.setIgnoreCertificateErrors',ignore:true)
  c.call('Emulation.setDeviceMetricsOverride',width:1360,height:960,deviceScaleFactor:1,mobile:false)
  c.call('Page.navigate',url:base+'index.html')
  c.wait_for("!!#{ui}.querySelector('[data-action=list]')")
  click.call(c,'[data-action=list]')
 end
 a,b=browsers.map(&:cdp)
 check.call('two isolated browsers show shared-review mode',a.evaluate("#{ui}.querySelector('.comments small').textContent==='团队评审'") && b.evaluate("#{ui}.querySelector('.comments small').textContent==='团队评审'"))
 click.call(a,'[data-action=list]');click.call(a,'[data-action=toggle]')
 a.step({'action'=>'click','selector'=>'#page-title'})
 a.wait_for("!!#{ui}.querySelector('#note-input')")
 a.evaluate("#{ui}.querySelector('#note-input').focus()")
 a.call('Input.insertText',text:'Temporary isolated HTTPS evidence; no formal data.')
 a.evaluate(<<~JS)
 (()=>{const canvas=document.createElement('canvas');canvas.width=4;canvas.height=4;const bytes=Uint8Array.from(atob(canvas.toDataURL().split(',')[1]),x=>x.charCodeAt(0)),data=new DataTransfer();data.items.add(new File([bytes],'tls-reference.png',{type:'image/png'}));#{ui}.querySelector('#note-input').dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,composed:true,cancelable:true}));})()
 JS
 a.wait_for("#{ui}.querySelectorAll('.attachment-drafts img').length===1&&!#{ui}.querySelector('[data-action=save]').disabled")
 click.call(a,'[data-action=save]')
 a.wait_for("!#{ui}.querySelector('#note-input')&&#{ui}.querySelectorAll('.comment').length===1",30)
 b.wait_for("#{ui}.querySelectorAll('.comment').length===1",25)
 check.call('HTTPS peer automatically synchronizes browser-saved comment',true)
 saved=b.evaluate("fetch(#{(base+'__review/comments').to_json}).then(r=>r.json()).then(d=>d.comments[0])")
 b.wait_for("#{ui}.querySelector('.attachment img')?.naturalWidth===4")
 check.call('HTTPS screenshot and attachment load under prefix',b.evaluate("Promise.all([#{saved['screenshot'].to_json},#{saved['attachments'][0]['url'].to_json}].map(u=>fetch(u).then(r=>r.ok))).then(x=>x.every(Boolean))"))
 click.call(a,"[data-action=edit][data-id='#{saved['id']}']")
 # The peer performs a guarded technical-completion write, leaving user acceptance untouched.
 changed=b.evaluate("(async()=>{const x=await(await fetch(#{(base+'__review/comments').to_json})).json(),c=x.comments[0];const r=await fetch(#{(base+'__review/comments').to_json},{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({projectId:'field-notes-shared-isolated',comment:{...c,status:'changed',resolution:'Temporary HTTPS smoke verified'},expectedUpdate:c.updatedAt})});return r.status})()")
 raise 'Guarded shared update failed' unless changed==200
 click.call(a,'[data-action=refresh]')
 a.wait_for("#{ui}.querySelector('.comment-head span')?.textContent==='待验收'")
 a.evaluate("#{ui}.querySelector('#note-input').focus();#{ui}.querySelector('#note-input').select()")
 a.call('Input.insertText',text:'Stale edit must remain here after conflict')
 click.call(a,'[data-action=save]')
 a.wait_for("#{ui}.querySelector('.error')?.textContent.includes('已更新')")
 check.call('HTTPS stale editor is rejected and draft retained',a.evaluate("#{ui}.querySelector('#note-input').value==='Stale edit must remain here after conflict'"))
 latest=b.evaluate("fetch(#{(base+'__review/comments').to_json}).then(r=>r.json()).then(d=>d.comments[0])")
 check.call('HTTPS conflict preserves peer status body and original evidence',latest['status']=='changed' && latest['text']==saved['text'] && latest['screenshot']==saved['screenshot'] && latest['attachments']==saved['attachments'])
 browsers.first.screenshot(File.join(out,'shared-https-conflict.png'))
 errors=browsers.flat_map{|browser|browser.cdp.events.select{|e|e['method']=='Runtime.exceptionThrown'}}
 check.call('HTTPS browsers report no runtime exception',errors.empty?)
 File.write(File.join(out,'shared-browser-results.json'),JSON.pretty_generate(checks:checks,selfSignedCertificateAcceptedOnlyViaCDP:true))
ensure
 browsers.each(&:close)
end
