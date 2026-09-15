// Keep the pinned browser location independent of the MCP client's env allowlist.
process.env.PLAYWRIGHT_BROWSERS_PATH = '/opt/browsers';
const {spawn} = require('node:child_process');
const {createInterface} = require('node:readline');
const path = require('node:path');
const {chromium} = require('playwright');
const {boundImages} = require('./image-response.cjs');
const child = spawn(process.execPath, [path.join(__dirname, 'node_modules/@playwright/mcp/cli.js'),
  '--headless', '--isolated', '--no-sandbox', '--executable-path', chromium.executablePath(),
  '--image-responses', 'allow', '--caps', 'vision', '--output-dir', '/workspace/source/review',
  ...process.argv.slice(2)], {stdio:['pipe','pipe','inherit']});
// This MCP version returns image content only for automatically named screenshots.
// Hide the optional filename parameter and enforce that behavior even for old clients.
createInterface({input:process.stdin}).on('line', line=>{
  const message=JSON.parse(line);
  if(message.method==='tools/call' && message.params?.name==='browser_take_screenshot')
    delete message.params.arguments?.filename;
  child.stdin.write(JSON.stringify(message)+'\n');
}).on('close',()=>child.stdin.end());
let output = Promise.resolve();
createInterface({input:child.stdout}).on('line',line=>{
  output = output.then(async()=>{
  const message=JSON.parse(line);
  for(const tool of message.result?.tools || []) if(tool.name==='browser_take_screenshot') {
    delete tool.inputSchema.properties.filename;
    tool.description += ' Returns bounded image content directly and saves an automatically named original file under source/review. Large image previews are compressed for transport. Use the returned file path in review evidence.';
  }
  process.stdout.write(JSON.stringify(await boundImages(message))+'\n');
  }).catch(error=>{process.stderr.write(error.message+'\n');child.kill();process.exitCode=1;});
});
for (const signal of ['SIGTERM','SIGINT']) process.on(signal,()=>child.kill(signal));
child.on('exit',code=>output.finally(()=>process.exit(process.exitCode || code || 0)));
child.on('error',error=>{process.stderr.write(error.message+'\n');process.exit(1);});
