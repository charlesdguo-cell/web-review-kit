require_relative 'cdp'
require 'tmpdir'
require 'fileutils'

# Isolated browser; never connects to or changes the user's browser profile.
class PrototypeBrowser
  attr_reader :cdp, :directory
  def initialize
    @directory = Dir.mktmpdir('ikigen-browser-')
    socket = TCPServer.new('127.0.0.1', 0)
    port = socket.addr[1]
    socket.close
    chrome = ENV.fetch('CHROME_BIN', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    @pid = Process.spawn(chrome, '--headless=new', '--no-first-run', '--no-default-browser-check',
      '--remote-debugging-address=127.0.0.1', "--remote-debugging-port=#{port}",
      "--user-data-dir=#{@directory}/profile", 'about:blank', out: "#{@directory}/browser.log", err: [:child, :out])
    Timeout.timeout(20) do
      loop do
        begin
          @cdp = ReviewCDP.new(port)
          break
        rescue Errno::ECONNREFUSED, EOFError, JSON::ParserError, KeyError
          sleep 0.1
        end
      end
    end
  end

  def screenshot(path)
    FileUtils.mkdir_p(File.dirname(path))
    result = @cdp.call('Page.captureScreenshot', format: 'png', captureBeyondViewport: false)
    File.binwrite(path, Base64.decode64(result.fetch('data')))
  end

  def close
    Process.kill('TERM', @pid) rescue nil
    Process.wait(@pid) rescue nil
    FileUtils.remove_entry(@directory) if @directory && File.exist?(@directory)
  end
end
