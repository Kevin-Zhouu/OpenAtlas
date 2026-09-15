const sharp = require('sharp');

// Codex's JSON activity trace truncates oversized tool results even when the
// model received the image. Bound previews so the publication evidence probe can
// verify complete image blocks; original screenshot files stay untouched.
async function boundImages(message) {
  const content = message.result?.content;
  if (!Array.isArray(content)) return message;
  const images = content.filter(block => block.type === 'image');
  const budget = Math.floor(600000 / Math.max(1, images.length));
  for (const block of images) {
    if (block.data.length <= budget) continue;
    const original = Buffer.from(block.data, 'base64');
    let encoded;
    for (const size of [1600, 1280, 1024, 800, 640, 480, 320]) {
      encoded = await sharp(original).resize({width:size, height:size, fit:'inside', withoutEnlargement:true})
        .flatten({background:'#ffffff'}).jpeg({quality:80}).toBuffer();
      if (Math.ceil(encoded.length / 3) * 4 <= budget) break;
    }
    if (Math.ceil(encoded.length / 3) * 4 > budget) throw new Error('Review image exceeds the tool transport budget');
    block.data = encoded.toString('base64');
    block.mimeType = 'image/jpeg';
  }
  return message;
}

module.exports = {boundImages};
