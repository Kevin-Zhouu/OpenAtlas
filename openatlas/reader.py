"""A narrow navigation bridge, executed inside the existing opaque reader sandbox."""
import re

BRIDGE = r'''<style id="openatlas-reader-style">
#contents-nav,nav[aria-label="Notebook contents"]{display:none!important}
html{scroll-padding-top:88px!important}body{padding-top:64px!important}
</style><script>
(() => {
  let sections = [];
  function outline() {
    sections = Array.from(document.querySelectorAll('main h1, main h2, article h1, article h2'));
    if (!sections.length) sections = Array.from(document.querySelectorAll('h1,h2'));
    sections = sections.filter(el => !el.closest('nav') && el.textContent.trim()).slice(0,150);
    document.querySelectorAll('nav').forEach(nav => {
      const toggle = nav.querySelector('button[aria-controls]');
      if (toggle && /^(contents|table of contents)$/i.test((toggle.getAttribute('aria-label') || toggle.textContent).replace(/[☰≡]/g,'').trim())) nav.style.setProperty('display','none','important');
    });
    parent.postMessage({type:'openatlas:outline', items:sections.map(el => el.textContent.trim().slice(0,160))}, '*');
  }
  let pending = false;
  function reportScroll() { parent.postMessage({type:'openatlas:scroll', y: Math.max(0, window.scrollY)}, '*'); pending = false; }
  window.addEventListener('scroll', () => { if (!pending) { pending = true; requestAnimationFrame(reportScroll); } }, {passive:true});
  window.addEventListener('message', event => {
    if (event.source !== parent || !event.data) return;
    if (event.data.type === 'openatlas:outline-request') { outline(); reportScroll(); }
    if (event.data.type === 'openatlas:section' && Number.isInteger(event.data.index)) {
      const target = sections[event.data.index];
      if (target) { target.scrollIntoView({behavior:'instant',block:'start'}); target.setAttribute('tabindex','-1'); target.focus({preventScroll:true}); }
    }
  });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', outline); else outline();
})();
</script>'''


def reader_document(content):
    # A separate no-store reader response; immutable stored artifacts stay intact.
    if re.search(r'</head\s*>', content, re.I):
        return re.sub(r'</head\s*>', lambda _: BRIDGE + '</head>', content, count=1, flags=re.I)
    return BRIDGE + content
