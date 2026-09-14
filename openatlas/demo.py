"""Deterministic authored lesson. Explicitly demo, never a substitute for inference."""

import html
import json
import shutil
import time


def generate(workspace, request, progress):
    progress("Building the interactive demo Notebook")
    time.sleep(1.5)
    title = "A visual introduction to caching"
    prompt = html.escape(request["prompt"])
    body = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>A visual introduction to caching</title><style>
:root{font-family:system-ui,sans-serif;color:#193c32;background:#fbfaf6}*{box-sizing:border-box}body{margin:0}main{max-width:860px;margin:auto;padding:60px 28px 100px}header{border-bottom:1px solid #d7ded5;padding-bottom:35px}small,.eyebrow{font:600 11px system-ui;letter-spacing:2px;text-transform:uppercase;color:#55786a}h1{font:normal clamp(42px,7vw,72px)/1.07 Georgia,serif;letter-spacing:-2px;margin:24px 0}h2{font:normal 34px Georgia;margin:0 0 22px}p{font-size:17px;line-height:1.85;max-width:670px;color:#4b6058}section{padding-top:58px}aside{font-size:13px;line-height:1.6;background:#edf2e9;padding:16px 20px;border-radius:8px}nav{display:flex;gap:24px;padding-top:26px;flex-wrap:wrap}a{color:#245b46}button{border:1px solid #b3c9b9;border-radius:6px;padding:13px 20px;background:#174e39;color:white;cursor:pointer;font-size:15px}button:focus-visible,input:focus-visible{outline:3px solid #cda94f;outline-offset:4px}.lab{background:#eef3eb;padding:28px;border-radius:12px;margin:30px 0}.tokens{display:flex;gap:8px;margin:25px 0;flex-wrap:wrap}.token{border:1px solid #91b39b;background:white;border-radius:5px;padding:17px 20px;font:22px Georgia}.cached{background:#21573e;color:white}.metric{font:42px Georgia;margin:24px 0 8px}.caption{font-size:13px;line-height:1.6;color:#557267}input{width:100%;accent-color:#21573e;margin:24px 0}label{display:block;font-size:15px}#feedback{min-height:60px}footer{margin-top:60px;border-top:1px solid #d7ded5;padding-top:20px;font-size:12px;color:#668073}@media(prefers-reduced-motion:no-preference){.token{transition:background .25s}}@media(max-width:500px){main{padding:30px 20px}.lab{padding:20px}h1{letter-spacing:-1px}}
</style></head><body><main><header><small>OpenAtlas / Demo Notebook / 8 minute exploration</small><h1>Remember the work.<br>Skip the repetition.</h1><p>An interactive introduction to caching: why remembering yesterday’s calculation can make tomorrow’s answer faster.</p><aside><strong>Demo content.</strong> This is a fixed, authored caching lesson used to test OpenAtlas. It is not an AI-generated answer to your request.<br>Your request: PROMPT</aside><nav><a href="#idea">01 · The idea</a><a href="#experiment">02 · Try it</a><a href="#check">03 · Check your intuition</a></nav></header>
<section id="idea"><div class="eyebrow">01 / Start with an intuition</div><h2>A little memory saves a lot of work.</h2><p>Imagine looking up the same word in a dictionary ten times. You could find the page every time. Or you could leave a bookmark. A cache is that bookmark: a saved result you can reuse when the same work comes around again.</p><p>You only need one prerequisite here: a calculation takes time, and a saved answer takes space. Caching trades some of that space for less repeated work.</p></section>
<section id="experiment"><div class="eyebrow">02 / A small experiment</div><h2>Build a sentence, one token at a time.</h2><p>A language model produces a sequence of tokens. At each step, it uses information about earlier tokens. A key-value cache retains earlier key and value vectors so the model can reuse them. It still computes attention against the stored history; caching does not remove that work.</p><div class="lab"><label for="length">How many tokens are in the sequence?</label><input id="length" type="range" min="2" max="12" value="4"><div class="tokens" id="tokens"></div><button id="toggle">Enable caching</button><div id="cost" class="metric" aria-live="polite">10 calculations</div><div class="caption" id="explanation">Without caching: 1 + 2 + 3 + 4 = 10 token projections.</div></div><p>This toy model counts repeated key/value projections, not total inference time. Without reuse, a sequence of n tokens requires 1 + 2 + … + n token projections in this simplified example. With reuse, each token is projected once: n projections. Real inference also includes attention, feed-forward layers, memory transfer, and other costs.</p><p>PagedAttention addresses a related space problem: how to arrange the saved vectors in memory. Think of numbered pages in a notebook. Pages need not sit next to each other, provided you keep an index that tells you where to find them. This demo stops at the caching intuition; a generated Notebook can explore the full memory layout.</p></section>
<section id="check"><div class="eyebrow">03 / Make the idea yours</div><h2>What does the cache actually save?</h2><p>If a sequence grows from four tokens to five, which work can a key-value cache reuse?</p><button id="wrong">The entire next prediction</button> <button id="right">Earlier key/value projections</button><p id="feedback" aria-live="polite">Choose an answer to reveal the explanation.</p><p>Try this exercise: set the sequence to twelve tokens, then switch caching on and off. Explain why the gap grows. What resource must grow as you keep more history?</p></section><footer>OpenAtlas · Authored demo · Your Notebook lives in your local library.</footer></main><script>
let cached=false;const length=document.querySelector('#length');function render(){const n=Number(length.value);document.querySelector('#tokens').innerHTML=Array.from({length:n},(_,i)=>`<span class="token ${cached&&i<n-1?'cached':''}">${i+1}</span>`).join('');document.querySelector('#cost').textContent=`${cached?n:n*(n+1)/2} calculations`;document.querySelector('#explanation').textContent=cached?'With caching: each token is projected once. Green tokens reuse saved vectors.':`Without caching: ${Array.from({length:n},(_,i)=>i+1).join(' + ')} = ${n*(n+1)/2} token projections.`;document.querySelector('#toggle').textContent=cached?'Disable caching':'Enable caching'}length.oninput=render;document.querySelector('#toggle').onclick=()=>{cached=!cached;render()};document.querySelector('#right').onclick=()=>document.querySelector('#feedback').textContent='Exactly. Earlier key/value projections can be reused. The new token still needs computation, and attention still reads the history.';document.querySelector('#wrong').onclick=()=>document.querySelector('#feedback').textContent='Not quite. A new prediction depends on the new context. The cache saves earlier key/value projections, not the whole prediction.';render();</script></body></html>""".replace(
        "PROMPT", prompt
    )
    source = workspace / "source"
    dist = workspace / "dist"
    source.mkdir(exist_ok=True)
    dist.mkdir(exist_ok=True)
    (source / "index.html").write_text(body)
    (source / "build.py").write_text(
        "from pathlib import Path\nimport shutil\nshutil.copytree(Path(__file__).parent, Path(__file__).parent.parent/'dist', dirs_exist_ok=True, ignore=shutil.ignore_patterns('build.py','README.md'))\n"
    )
    (source / "README.md").write_text(
        "Authored OpenAtlas demo. Build: python source/build.py. Interaction tests are in the retained manifest.json. No model inference is used.\n"
    )
    shutil.copy(source / "index.html", dist / "index.html")
    manifest = {
        "title": title,
        "description": "An authored, interactive demo of caching.",
        "entrypoint": "index.html",
        "demo": True,
        "checks": [
            {
                "selector": "#toggle",
                "action": "click",
                "expect_selector": "#cost",
                "expect_text": "4 calculations",
            },
            {
                "selector": "#length",
                "action": "range",
                "value": "8",
                "expect_selector": "#cost",
                "expect_text": "8 calculations",
            },
            {
                "selector": "#right",
                "action": "click",
                "expect_selector": "#feedback",
                "expect_text": "Exactly.",
            },
            {
                "selector": "#wrong",
                "action": "click",
                "expect_selector": "#feedback",
                "expect_text": "Not quite.",
            },
        ],
    }
    (workspace / "manifest.json").write_text(json.dumps(manifest))
