const {test} = require('node:test');
const assert = require('node:assert/strict');
const {randomBytes} = require('node:crypto');
const sharp = require('sharp');
const {boundImages} = require('./image-response.cjs');

test('large PNG screenshots remain image blocks below the CLI trace limit', async()=>{
  const png = await sharp(randomBytes(2400*1600*3), {raw:{width:2400,height:1600,channels:3}}).png().toBuffer();
  assert(png.length > 1048576);
  const message = {jsonrpc:'2.0',id:3,result:{content:[
    {type:'text',text:'Original screenshot: source/review/large.png'},
    {type:'image',mimeType:'image/png',data:png.toString('base64')}
  ]}};
  await boundImages(message);
  assert(JSON.stringify(message).length < 800000);
  assert.equal(message.result.content[1].type,'image');
  assert.equal(message.result.content[1].mimeType,'image/jpeg');
  const metadata = await sharp(Buffer.from(message.result.content[1].data,'base64')).metadata();
  assert(metadata.width > 300 && metadata.width <= 1600);
  assert.equal(message.result.content[0].text,'Original screenshot: source/review/large.png');
});

test('small screenshots and non-image tool responses are unchanged',async()=>{
  const png = await sharp({create:{width:32,height:32,channels:3,background:'white'}}).png().toBuffer();
  const message={result:{content:[{type:'image',mimeType:'image/png',data:png.toString('base64')}]}};
  const before=JSON.stringify(message);
  await boundImages(message);
  assert.equal(JSON.stringify(message),before);
  const listing={result:{tools:[{name:'browser_navigate'}]}};
  assert.equal(await boundImages(listing),listing);
});
