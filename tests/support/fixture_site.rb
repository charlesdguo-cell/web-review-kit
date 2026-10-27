require 'fileutils'
require 'json'
require 'zlib'

# Synthetic pages only: no business components, assets, build, or formal comments.
module ReviewFixtureSite
  def self.create(site, root)
    FileUtils.mkdir_p(site)
    assets = File.join(site, 'review-assets')
    FileUtils.mkdir_p(assets)
    %w[review.js review.css html2canvas.min.js].each do |name|
      FileUtils.cp(File.join(root, 'runtime', name), File.join(assets, name))
    end
    html = <<~HTML
      <!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
      <title>Independent review fixture</title>
      <script src="review-assets/review.js" data-prototype-review></script>
      <style>
        body{margin:60px;font:18px sans-serif;background:#eef0f7;color:#17213a;min-height:1400px}
        #fixture-world{width:700px;padding:24px;background:white;transform:translateX(0)}
        button,a{display:block;margin:16px 0;padding:14px}#fixture-dialog{padding:50px;position:fixed;inset:100px auto auto 140px;background:#f8f0ff;z-index:20}
        .photo{position:relative;isolation:isolate;width:480px;height:180px;background:#ddd}
        .photo::before{content:'';position:absolute;inset:0;z-index:-1;background-image:url('gradient.svg');background-size:cover}
      </style></head><body><main id="fixture-world">
      <h1 id="fixture-title">独立合成页面</h1><button id="open-dialog">打开测试弹窗</button>
      <a id="fixture-link" href="other.html">另一个页面</a><div class="photo"></div>
      <div id="fixture-dialog" role="dialog" hidden><button id="dialog-action">弹窗动作</button><button id="close-dialog">关闭</button></div>
      </main><script>
        window.dialogActions=0;document.querySelector('#open-dialog').onclick=()=>document.querySelector('#fixture-dialog').hidden=false;
        document.querySelector('#dialog-action').onclick=()=>dialogActions++;
        document.querySelector('#close-dialog').onclick=()=>document.querySelector('#fixture-dialog').hidden=true;
        let start=null;const world=document.querySelector('#fixture-world');
        world.addEventListener('pointerdown',e=>start=e.clientX);
        world.addEventListener('pointermove',e=>{if(start!==null&&e.buttons)world.style.transform='translateX('+(e.clientX-start)+'px)'});
        window.addEventListener('pointerup',()=>start=null);
      </script></body></html>
    HTML
    File.write(File.join(site, 'index.html'), html)
    File.write(File.join(site, 'other.html'), html)
    File.write(File.join(site, 'gradient.svg'), '<svg xmlns="http://www.w3.org/2000/svg" width="480" height="180"><defs><linearGradient id="a"><stop stop-color="#ff0000"/><stop offset=".5" stop-color="#00ff00"/><stop offset="1" stop-color="#0000ff"/></linearGradient><linearGradient id="b" x2="0" y2="1"><stop stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff"/></linearGradient></defs><rect width="480" height="180" fill="url(#a)"/><rect width="480" height="180" fill="url(#b)"/></svg>')
    File.write(File.join(site, 'text.html'), '<!doctype html><html><head><meta charset="utf-8"><style>body{margin:100px;font:24px sans-serif}</style></head><body><p id="text-target">准确选中文字，讨论文案修改。</p></body></html>')
  end

  def self.seed_reviews(data)
    FileUtils.mkdir_p(File.join(data, 'screenshots'))
    # A real, deterministic RGB PNG with enough detail to verify the body size.
    chunk = lambda { |kind, body| [body.bytesize].pack('N') + kind + body + [Zlib.crc32(kind + body)].pack('N') }
    pixels = (0...32).map do |y|
      "\0".b + (0...32).flat_map { |x| [(x*17+y*7)%256, (x*13+y*23)%256, (x*31+y*11)%256] }.pack('C*')
    end.join
    image = "\x89PNG\r\n\x1a\n".b + chunk.call('IHDR', [32,32,8,2,0,0,0].pack('NNC5')) +
      chunk.call('IDAT', Zlib::Deflate.deflate(pixels)) + chunk.call('IEND', ''.b)
    File.binwrite(File.join(data, 'screenshots/fixture-shared-001.png'), image)
    File.write(File.join(data, 'comments.json'), JSON.generate([{
      id:'fixture-shared-001',number:1,text:'独立共享评论',status:'open',createdAt:'1',updatedAt:'1',
      page:{path:'/index.html',title:'Independent review fixture'},anchor:{selector:'#fixture-title',label:'独立合成页面'},
      screenshot:'/__review/screenshots/fixture-shared-001.png',attachments:[]
    }]))
  end
end
