require 'socket'
require 'net/http'
require 'json'
require 'base64'
require 'securerandom'
require 'timeout'
require 'uri'

class ReviewCDP
  attr_reader :events
  def initialize(port = 9222)
    target = JSON.parse(Net::HTTP.get(URI("http://127.0.0.1:#{port}/json/list"))).find { |t| t['type'] == 'page' }
    uri = URI(target.fetch('webSocketDebuggerUrl'))
    @socket = TCPSocket.new(uri.host, uri.port)
    key = Base64.strict_encode64(SecureRandom.random_bytes(16))
    @socket.write("GET #{uri.path} HTTP/1.1\r\nHost: #{uri.host}:#{uri.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: #{key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
    header = ''; header << @socket.read(1) until header.end_with?("\r\n\r\n")
    raise header unless header.match?(/^HTTP\/1\.[01] 101 /)
    @id = 0; @events = []
    call('Runtime.enable'); call('Page.enable')
  end
  def write_frame(data, opcode = 1)
    data = data.b; n = data.bytesize; mask = SecureRandom.random_bytes(4).bytes
    header = [0x80 | opcode]
    header += n < 126 ? [0x80 | n] : n < 65536 ? [0x80 | 126, *[n].pack('n').bytes] : [0x80 | 127, *[n].pack('Q>').bytes]
    payload = data.bytes.each_with_index.map { |b,i| b ^ mask[i % 4] }.pack('C*')
    @socket.write(header.pack('C*') + mask.pack('C*') + payload)
  end
  def read_frame
    data = ''.b
    loop do
      header = @socket.read(2).bytes; marker = header[1] & 127
      length = case marker
      when 126 then @socket.read(2).unpack1('n')
      when 127 then @socket.read(8).unpack1('Q>')
      else marker
      end
      mask = (header[1] & 128) != 0 ? @socket.read(4).bytes : nil
      part = @socket.read(length)
      part = part.bytes.each_with_index.map { |b,i| b ^ mask[i % 4] }.pack('C*') if mask
      opcode = header[0] & 15
      if opcode == 9; write_frame(part,10); next; end
      next if opcode == 10
      raise 'Browser socket closed' if opcode == 8
      data << part
      return JSON.parse(data.force_encoding('UTF-8')) if (header[0] & 128) != 0
    end
  end
  def call(method, params = {})
    @id += 1; wanted = @id
    write_frame(JSON.generate(id:wanted, method:method, params:params))
    Timeout.timeout(25) do
      loop do
        msg = read_frame
        if msg['id'] == wanted
          raise JSON.generate(msg['error']) if msg['error']
          return msg['result']
        end
        @events << msg if msg['method']
      end
    end
  end
  def evaluate(expression)
    r = call('Runtime.evaluate',expression:expression,returnByValue:true,awaitPromise:true)
    raise JSON.generate(r['exceptionDetails']) if r['exceptionDetails']
    r.dig('result','value')
  end
  def wait_for(expression, seconds = 15)
    Timeout.timeout(seconds) do
      loop do
        begin; return true if evaluate(expression); rescue StandardError; end
        sleep 0.1
      end
    end
  end
  def node_expression(step)
    css = JSON.generate(step.fetch('selector'))
    step['action'] == 'click' && step['text'] ? "[...document.querySelectorAll(#{css})].find(e=>e.textContent.trim()===#{JSON.generate(step['text'])})" : "document.querySelector(#{css})"
  end
  def step(s)
    case s.fetch('action')
    when 'navigate'
      call('Page.navigate',url:s.fetch('url')); wait_for("document.readyState==='complete' && !!document.querySelector('.app')")
    when 'viewport'
      call('Emulation.setDeviceMetricsOverride',width:s.fetch('width'),height:s.fetch('height'),deviceScaleFactor:1,mobile:false)
    when 'eval'; evaluate(s.fetch('expression'))
    when 'protocol'; call(s.fetch('method'),s['params'] || {})
    when 'download_ready'
      Timeout.timeout(15) do
        loop do
          paths = Dir[File.join(File.dirname(__FILE__),'downloads','*.txt')]
          return paths.map { |p| {file:File.basename(p),text:File.read(p)} } unless paths.empty?
          sleep 0.1
        end
      end
    when 'wait'; wait_for(s.fetch('expression'),s['seconds'] || 15)
    when 'click'
      p = evaluate("(()=>{const e=#{node_expression(s)};if(!e)throw Error('Missing click target');e.scrollIntoView({block:'nearest'});const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
      call('Input.dispatchMouseEvent',type:'mousePressed',x:p['x'],y:p['y'],button:'left',clickCount:1)
      call('Input.dispatchMouseEvent',type:'mouseReleased',x:p['x'],y:p['y'],button:'left',clickCount:1)
      sleep 0.12
      true
    when 'fill'
      evaluate("(()=>{const e=#{node_expression(s)};e.focus();e.select();})()")
      call('Input.insertText',text:s.fetch('text')); sleep 0.12; true
    when 'key'
      code = {'Enter'=>13,'Escape'=>27,'ArrowDown'=>40,'ArrowUp'=>38}.fetch(s.fetch('key'))
      call('Input.dispatchKeyEvent',type:'keyDown',key:s['key'],code:s['key'],windowsVirtualKeyCode:code)
      call('Input.dispatchKeyEvent',type:'keyUp',key:s['key'],code:s['key'],windowsVirtualKeyCode:code)
      sleep 0.1; true
    when 'screenshot'
      sleep 0.15
      image = call('Page.captureScreenshot',format:'png',captureBeyondViewport:false)
      File.binwrite(File.join(File.dirname(__FILE__),s.fetch('file')),Base64.decode64(image.fetch('data')))
      s['file']
    else; raise "Unknown action #{s['action']}"
    end
  end
end
