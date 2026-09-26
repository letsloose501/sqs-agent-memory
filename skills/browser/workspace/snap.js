// One-call page snapshot: numbered visible controls + visible text.
// Ported from browser-use/jev-ultrafast (snapshot.js, MIT) and simplified for an agent
// that reads the table: no guards/marker, a select is one line, links carry href.
// Element identity lives in window.__bh, so ref e5 survives the next browser-harness
// call (a new python process) as long as the page stays the same.
(opts => {
  if (!document.body) return null;
  const all = !!opts.all, maxText = opts.text ?? 3000, maxItems = opts.limit ?? 150;
  const bh = window.__bh ||= {ids: new WeakMap(), nodes: new Map(), next: 1, refs: {}};
  const identity = e => {
    if (!bh.ids.has(e)) bh.ids.set(e, bh.next++);
    const id = bh.ids.get(e); bh.nodes.set(id, e); return id;
  };
  for (const [id, e] of bh.nodes) if (!e.isConnected) bh.nodes.delete(id);
  const safe = e => !['password', 'hidden'].includes(e.type);
  const visible = e => !e.closest('[aria-hidden="true"],[inert]') &&
    e.checkVisibility({checkOpacity: true, checkVisibilityCSS: true});
  const name = (e, seen = new Set()) => {
    if (!e || seen.has(e)) return '';
    seen.add(e);
    const referenced = (e.getAttribute('aria-labelledby') || '').split(/\s+/)
      .map(id => name(document.getElementById(id), seen)).filter(Boolean).join(' ');
    return referenced || e.getAttribute('aria-label') ||
      [...(e.labels || [])].map(l => name(l, seen)).filter(Boolean).join(' ') ||
      (['button', 'submit', 'reset'].includes(e.type) ? e.value : '') || e.getAttribute('alt') ||
      (e.tagName === 'INPUT' ? '' : [...e.childNodes].map(n => n.nodeType === 3 ? n.textContent :
        n.nodeType === 1 && n.getAttribute('aria-hidden') !== 'true' ? name(n, seen) : '').join(' ').trim()) ||
      e.getAttribute('title') || e.getAttribute('placeholder') || e.getAttribute('name') || '';
  };
  const roles = ['button', 'link', 'checkbox', 'radio', 'switch', 'tab', 'menuitem', 'menuitemradio',
    'option', 'gridcell', 'combobox', 'textbox', 'searchbox', 'spinbutton', 'slider'];
  const selector = 'a[href],button,input,textarea,select,summary,[contenteditable="true"],' +
    roles.map(r => '[role="' + r + '"]').join(',');
  const role = e => {
    const explicit = e.getAttribute('role');
    if (roles.includes(explicit)) return explicit;
    if (e.tagName === 'BUTTON' || e.tagName === 'SUMMARY') return 'button';
    if (e.tagName === 'A') return 'link';
    if (e.tagName === 'SELECT') return 'select';
    if (e.tagName === 'TEXTAREA' || e.isContentEditable) return 'textbox';
    if (e.tagName === 'INPUT') {
      if (['checkbox', 'radio'].includes(e.type)) return e.type;
      if (['button', 'submit', 'reset', 'image'].includes(e.type)) return 'button';
      if (e.type === 'file') return 'file';
      if (e.type === 'search') return 'searchbox';
      if (e.type === 'number' || e.type === 'range') return 'spinbutton';
      return 'textbox';
    }
    return null;
  };
  const clip = (s, n) => { s = (s || '').replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
  const items = [], refs = {};
  let offscreen = 0, covered = 0;
  // Is the element covered: something foreign (modal, sheet, banner) sits on its center.
  const onTop = (e, r) => {
    const x = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1);
    const y = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
    const t = document.elementFromPoint(x, y);
    return !t || t === e || e.contains(t) || t.contains(e) ||
      (e.labels && [...e.labels].some(l => l === t || l.contains(t)));
  };
  // Besides semantic controls take "clickable divs": cursor:pointer, the parent has none,
  // no real control inside. Catches search suggestions, cards, custom dropdowns.
  const cands = [...document.querySelectorAll(selector)];
  const seen = new Set(cands);
  for (const e of document.body.querySelectorAll('div,span,li,td,img,svg,p,h1,h2,h3,h4,label')) {
    if (seen.has(e) || e.closest(selector)) continue;
    if (e.closest('label')?.control) continue;  // a control's label: the control itself is already listed
    const r = e.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0 || r.bottom < 0 || r.top > innerHeight) continue;
    if (getComputedStyle(e).cursor !== 'pointer') continue;
    const p = e.parentElement;
    if (p && getComputedStyle(p).cursor === 'pointer') continue;
    if (e.querySelector(selector)) continue;
    e.__bhClickable = true; cands.push(e);
  }
  for (const e of cands) {
    if (!safe(e) || !visible(e) || e.matches(':disabled') || e.closest('[aria-disabled="true"]')) continue;
    const r = e.getBoundingClientRect(), rname = e.__bhClickable ? 'clickable' : role(e);
    if (!rname || r.width <= 0 || r.height <= 0) continue;
    const inView = r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
    if (!inView) { offscreen++; if (!all) continue; }
    else if (!onTop(e, r)) { covered++; if (!all) continue; }
    if (rname === 'gridcell' && e.querySelector('button,[role="button"]')) continue;
    if (items.length >= maxItems) continue;
    const ref = 'e' + (items.length + 1);
    // Label = the text a human sees; the accessible name only as an extra when it differs.
    // On YouTube the button "Отклонить все" has aria-label "Запретить использование файлов cookie…",
    // and a search by the visible text missed it (23.09.2026).
    const seenText = clip(['INPUT', 'SELECT', 'TEXTAREA'].includes(e.tagName) || e.isContentEditable ? '' : e.innerText, 70);
    const acc = clip(name(e), 70);
    const it = {ref, role: rname, label: seenText || acc};
    if (seenText && acc && acc !== seenText && !acc.includes(seenText)) it.aria = clip(acc, 50);
    refs[ref] = identity(e);
    if (!inView) it.off = true;
    for (const k of ['checked', 'selected', 'expanded']) {
      const v = e.getAttribute('aria-' + k); if (v !== null) it[k] = v;
    }
    if (['checkbox', 'radio'].includes(e.type)) it.checked = String(e.checked);
    if (e.tagName === 'SELECT') {
      it.value = clip([...e.selectedOptions].map(o => o.label).join(', '), 40);
      it.options = e.options.length;
    } else if ('value' in e && !['button', 'checkbox', 'radio'].includes(rname) && e.tagName !== 'LI') {
      if (e.value) it.value = clip(String(e.value), 60);
    } else if (e.isContentEditable) {
      const v = e.innerText.trim(); if (v) it.value = clip(v, 60);
    }
    if (e.tagName === 'A') {
      const h = e.getAttribute('href') || '';
      if (h && !h.startsWith('javascript:')) it.href = clip(h, 80);
    }
    items.push(it);
  }
  bh.refs = refs; bh.url = location.href;
  const words = [], walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const range = document.createRange(); let node, length = 0;
  while ((node = walker.nextNode()) && length < maxText) {
    const value = node.textContent.trim(), parent = node.parentElement;
    if (!value || !parent || parent.closest('script,style,noscript,template') || !visible(parent)) continue;
    range.selectNodeContents(node); const r = range.getBoundingClientRect();
    if (r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth) {
      words.push(value); length += value.length;
    }
  }
  return {url: location.href, title: document.title, text: words.join('\n').slice(0, maxText),
    scroll: {y: Math.round(scrollY), h: document.documentElement.scrollHeight, vh: innerHeight, vw: innerWidth},
    // Visibility is required: YouTube keeps four hidden role="dialog" nodes and the flag lied (23.09.2026).
    items, offscreen, covered, dialog: [...document.querySelectorAll('dialog[open],[role="dialog"],[aria-modal="true"]')]
      .some(d => d.checkVisibility({checkOpacity: true, checkVisibilityCSS: true}) && d.getBoundingClientRect().height > 0)};
})
