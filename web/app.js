'use strict';
(() => {
  const $ = (selector) => document.querySelector(selector);
  const escape = (value) => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const views = ['discover', 'games', 'tools', 'saved'];
  const repoRoot = 'https://github.com/solarfren69420/Slopforge';
  let projects = [], favorites = new Set(), storageAvailable = true, toastTimer, searchTimer;
  const state = {view:'discover', q:'', category:'', platform:'', method:'', tag:'', sort:'featured'};
  const categoryIcons = {'Simulation':'▤','RPG':'♜','Adventure':'◇','Shooter':'⌖','Strategy':'⚑','Racing':'✣','Platformer':'▥','Sandbox':'▧','Graphic design':'◈','3D & VFX':'⬡','CAD & engineering':'⌑','GIS & science':'◎','Electronics & PCB':'⌘','Audio & video':'♫','Office & productivity':'▤','Game engines':'✣','Compatibility':'⇄','Reverse engineering':'⌬'};
  const platformShort = {Windows:'Win',Linux:'Linux',macOS:'Mac'};
  try { const parsed = JSON.parse(localStorage.getItem('slopforge-library') || '[]'); if (Array.isArray(parsed)) favorites = new Set(parsed.filter(x => typeof x === 'string')); } catch { storageAvailable = false; }

  function readRoute() {
    const params = new URLSearchParams(location.search);
    state.view = views.includes(params.get('view')) ? params.get('view') : 'discover';
    for (const key of ['q','category','platform','method','tag']) state[key] = (params.get(key) || '').slice(0,150);
    state.sort = ['featured','name','reviewed'].includes(params.get('sort')) ? params.get('sort') : 'featured';
    $('#search').value = state.q;
  }
  function writeRoute(push = false) {
    const url = new URL(location.href); url.search = '';
    for (const [key,value] of Object.entries(state)) if (value && !(key === 'view' && value === 'discover') && !(key === 'sort' && value === 'featured')) url.searchParams.set(key,value);
    if (url.href !== location.href) history[push ? 'pushState' : 'replaceState']({},'',url);
  }
  function notify(message) { clearTimeout(toastTimer); $('#toast').textContent = message; $('#toast').hidden = false; toastTimer = setTimeout(() => { $('#toast').hidden = true; },2800); }
  function baseProjects() { return projects.filter(p => state.view === 'games' || state.view === 'tools' ? p.kind === state.view : state.view === 'saved' ? favorites.has(p.id) : true); }
  function filteredProjects() {
    const words = state.q.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
    const list = baseProjects().filter(p => (!state.category || p.category === state.category) && (!state.platform || p.platforms.includes(state.platform)) && (!state.method || p.method === state.method) && (!state.tag || p.tags.includes(state.tag)) && words.every(word => [p.name,p.repo,p.description,p.category,p.method,p.language,...p.tags].join(' ').toLocaleLowerCase().includes(word)));
    return list.sort((a,b) => state.sort === 'name' ? a.name.localeCompare(b.name) : state.sort === 'reviewed' ? b.reviewed.localeCompare(a.reviewed) || a.name.localeCompare(b.name) : Number(b.featured) - Number(a.featured) || projects.indexOf(a)-projects.indexOf(b));
  }
  function sidebars() {
    const base = baseProjects(), categories = [...new Set(base.map(p => p.category))];
    $('#categories').innerHTML = categories.map(category => `<button class="side-button category-button ${state.category === category ? 'active' : ''}" data-category="${escape(category)}" aria-pressed="${state.category === category}"><span aria-hidden="true">${categoryIcons[category] || '◇'}</span>${escape(category)}<span class="count">${base.filter(p => p.category === category).length}</span></button>`).join('');
    $('#platforms').innerHTML = ['Windows','Linux','macOS'].map(platform => `<button class="side-button category-button ${state.platform === platform ? 'active' : ''}" data-platform="${platform}" aria-pressed="${state.platform === platform}"><span aria-hidden="true">${platform === 'Windows' ? '⊞' : platform === 'Linux' ? '⌁' : '◉'}</span>${platform}</button>`).join('');
    $('#platform-shortcuts').innerHTML = ['Windows','Linux','macOS'].map(platform => `<button class="platform-shortcut" data-platform="${platform}" aria-pressed="${state.platform === platform}"><span aria-hidden="true">${platform === 'Windows' ? '⊞' : platform === 'Linux' ? '⌁' : '◉'}</span><div><strong>${platform}</strong><small>Browse upstream-listed projects →</small></div></button>`).join('');
    $('#mobile-category').innerHTML = '<option value="">All categories</option>' + categories.map(category => `<option value="${escape(category)}">${escape(category)}</option>`).join('');
    $('#mobile-category').value = state.category;
    $('#mobile-platform').value = state.platform;
    const methods = [...new Set(base.map(p => p.method))];
    $('#method').innerHTML = '<option value="">All project types</option>' + methods.map(method => `<option value="${escape(method)}">${escape(method)}</option>`).join('');
    $('#method').value = state.method;
    $('#tags').innerHTML = ['BYOD','Multiplayer','Mod support','Creative','Compatibility','Code analysis','Experimental','Controller support','Game development'].map(tag => `<button class="tag-button ${state.tag === tag ? 'active' : ''}" data-tag="${escape(tag)}" aria-pressed="${state.tag === tag}">${escape(tag)}</button>`).join('');
    for (const button of document.querySelectorAll('[data-view]')) { button.classList.toggle('active',button.dataset.view === state.view); if (button.hasAttribute('aria-pressed')) button.setAttribute('aria-pressed', String(button.dataset.view === state.view)); }
    $('#saved-count').textContent = favorites.size;
  }
  function art(p, detail = false) { return `<div class="${detail ? 'detail-art' : 'card-art'}"><img src="assets/cards/${escape(p.id)}.svg" alt="" ${detail ? '' : 'loading="lazy"'}><div class="art-overlay"></div><span class="card-monogram" aria-hidden="true">${escape(p.monogram)}</span>${detail ? '' : `<span class="card-method">${escape(p.method)}</span>`}</div>`; }
  function card(p) {
    const saved = favorites.has(p.id);
    return `<article class="project-card ${p.kind === 'tools' ? 'tools-card' : ''}" data-project-id="${escape(p.id)}">${art(p)}<button class="save-button" data-save="${escape(p.id)}" aria-pressed="${saved}" aria-label="${saved ? 'Remove' : 'Save'} ${escape(p.name)} ${saved ? 'from' : 'to'} my library">${saved ? '♥' : '♡'}</button><div class="card-content"><h4 class="project-title"><a href="${escape(p.repo)}" target="_blank" rel="noopener noreferrer">${escape(p.name)}</a></h4><p class="project-owner">${escape(p.repo.replace('https://github.com/',''))}</p><p class="card-description">${escape(p.description)}</p><div class="card-tags">${p.tags.slice(0,2).map(tag => `<button class="badge ${tag === 'BYOD' ? 'byod' : tag === 'Experimental' ? 'purple' : ''}" data-tag="${escape(tag)}">${escape(tag)}</button>`).join('')}</div><div class="card-bottom"><div class="platform-list" aria-label="Upstream-listed platforms: ${escape(p.platforms.join(', '))}">${p.platforms.map(platform => `<span class="platform-badge" title="${platform}">${platformShort[platform]}</span>`).join('')}</div><button class="detail-button" data-detail="${escape(p.id)}" aria-label="View details for ${escape(p.name)}">Details +</button></div><a class="repo-button" href="${escape(p.repo)}" target="_blank" rel="noopener noreferrer">View GitHub <span aria-hidden="true">↗</span></a></div></article>`;
  }
  function shelves(list) {
    const filtered = state.q || state.category || state.platform || state.method || state.tag || state.sort !== 'featured' || state.view === 'saved';
    if (filtered) return [{title:state.view === 'saved' ? 'Your collection' : state.category || 'Explore the projects', symbol:'◇', subtitle:'Follow a project to its source.', list}];
    if (state.view === 'tools') return [...new Set(list.map(p => p.category))].map(category => ({title:category,symbol:categoryIcons[category],subtitle:'Independent projects. Open possibilities.',list:list.filter(p => p.category === category)}));
    const groups = [];
    const used = new Set();
    function add(title,symbol,subtitle,predicate,view) { const matches = list.filter(p => !used.has(p.id) && predicate(p)); if (matches.length) { matches.forEach(p => used.add(p.id)); groups.push({title,symbol,subtitle,list:matches,view}); } }
    add('Community game revivals','✦','Old favorites. A new chapter.',p => p.kind === 'games' && p.featured,'games');
    if (state.view === 'discover') add('Tools without the tollbooth','⚒','Create on your own terms.',p => p.kind === 'tools' && ['krita','blender','freecad','gimp'].includes(p.id),'tools');
    add('Keep the classics alive','↻','Engines, ports, and community persistence.',p => p.kind === 'games' && !['Original open-source game','Game creation platform'].includes(p.method),'games');
    add('Play it your way','✣','Original worlds. Community possibilities.',p => p.kind === 'games','games');
    add('The creative toolkit','◈','Draw it. Record it. Make it happen.',p => p.kind === 'tools' && ['Graphic design','Audio & video'].includes(p.category),'tools');
    add('Build something that matters','⬡','Design, science, productivity, and game creation.',p => p.kind === 'tools' && !['Compatibility','Reverse engineering'].includes(p.category),'tools');
    add('Under the hood','⌘','Compatibility and reverse engineering.',p => p.kind === 'tools','tools');
    return groups;
  }
  function render() {
    document.body.dataset.view = state.view; sidebars(); $('#sort').value = state.sort;
    const hero = {discover:['Play more.<br>Make more.<br><span>Own your tools.</span>','Game revivals. Creative powerhouses. Tools that put you in control. Welcome to the good kind of slop.'],games:['Old favorites.<br>New possibilities.<br><span>Keep playing.</span>','Community engines, source ports, and original open-source games. Find the people giving play its next chapter.'],tools:['Less lock-in.<br>More creating.<br><span>Make it yours.</span>','Independent creative tools, open engines, and compatibility layers. Your next great idea starts with the right tools.']};
    if (hero[state.view]) { $('#hero-title').innerHTML = hero[state.view][0]; $('#hero-description').textContent = hero[state.view][1]; }
    $('#catalog-title').innerHTML = ({discover:'Fresh from the forge',games:'A more playable tomorrow',tools:'Your next creative superpower',saved:'Your corner of the forge'}[state.view]) + '<span class="title-dot">.</span>';
    $('#catalog-eyebrow').textContent = {discover:'A LITTLE BIT OF EVERYTHING',games:'COMMUNITY GAME PROJECTS',tools:'OPEN TOOLS. OPEN POSSIBILITIES.',saved:'SAVED IN THIS BROWSER'}[state.view];
    const list = filteredProjects();
    $('#result-count').textContent = `${list.length} ${list.length === 1 ? 'project' : 'projects'}`;
    const anyFilter = Boolean(state.q || state.category || state.platform || state.method || state.tag || state.sort !== 'featured');
    $('#reset').hidden = !anyFilter;
    $('#active-filters').innerHTML = ['category','platform','method','tag'].filter(key => state[key]).map(key => `<button class="filter-chip" data-clear="${key}">${escape(state[key])} ×</button>`).join('');
    $('#shelves').innerHTML = shelves(list).filter(s => s.list.length).map(s => `<section class="shelf"><div class="shelf-heading"><div><span class="shelf-symbol" aria-hidden="true">${s.symbol}</span><h3>${escape(s.title)}</h3><p>${escape(s.subtitle)}</p></div>${s.view ? `<button class="text-button" data-view="${s.view}">Explore ${s.view} →</button>` : ''}</div><div class="cards">${s.list.map(card).join('')}</div></section>`).join('');
    $('#empty').hidden = list.length > 0;
    $('#empty-title').textContent = state.view === 'saved' && favorites.size === 0 ? 'Your library starts with a little curiosity.' : 'Nothing in this corner of the forge.';
    $('#empty-copy').textContent = state.view === 'saved' && favorites.size === 0 ? 'Tap the heart on any project to save it here. No account needed.' : 'Try a different search or clear your filters.';
  }
  function update(push = false) { writeRoute(push); render(); }
  function changeView(view) { if (!views.includes(view)) return; state.view = view; state.category = ''; state.method = ''; state.platform = ''; state.tag = ''; update(true); }
  function reset() { Object.assign(state,{q:'',category:'',platform:'',method:'',tag:'',sort:'featured'}); $('#search').value = ''; if(state.view === 'saved') state.view = 'discover'; update(true); }
  function save(id) {
    const p = projects.find(p => p.id === id); if (!p) return;
    if (favorites.has(id)) favorites.delete(id); else favorites.add(id);
    try { localStorage.setItem('slopforge-library',JSON.stringify([...favorites])); storageAvailable = true; } catch { storageAvailable = false; }
    notify(storageAvailable ? `${p.name} ${favorites.has(id) ? 'saved to' : 'removed from'} your library.` : 'Browser storage is unavailable. Your library will last for this session.');
    render(); document.querySelector(`[data-save="${id}"]`)?.focus({preventScroll:true});
  }
  function showDetail(id, setHash = true) {
    const p = projects.find(p => p.id === id); if (!p) return;
    $('#detail-body').innerHTML = `<div class="dialog-top"><span class="eyebrow">${escape(p.category)} / ${p.kind.toUpperCase()}</span><button class="close-button" data-close aria-label="Close project details">×</button></div>${art(p,true)}<h2 id="detail-title">${escape(p.name)}</h2><p>${escape(p.description)}</p><div class="detail-meta"><div><small>PROJECT TYPE</small>${escape(p.method)}</div><div><small>UPSTREAM-LISTED PLATFORMS</small>${escape(p.platforms.join(' / '))}</div><div><small>PRIMARY TECHNOLOGY</small>${escape(p.language)}</div><div><small>LISTING REVIEWED</small>${escape(p.reviewed)}</div></div><h3>Data & setup</h3><p class="source-note">${escape(p.data_note)}</p><h3>Know the source</h3><p>${escape(p.source_note)}</p><a class="detail-source" href="${escape(p.repo)}" target="_blank" rel="noopener noreferrer">${escape(p.repo)} ↗</a><p>Repository identity and basic purpose reviewed. Slopforge has not built or gameplay-tested this project. Check upstream documentation for current requirements, licensing, and support.</p><div class="dialog-actions"><a class="button primary" href="${escape(p.repo)}" target="_blank" rel="noopener noreferrer">View upstream GitHub ↗</a><button class="button glass" data-copy="${escape(p.id)}">Copy project link</button><a class="button glass" href="${repoRoot}/issues/new?template=correction.yml&title=${encodeURIComponent('Correction: '+p.name)}">Suggest a correction ↗</a></div>`;
    if (!$('#detail').open) $('#detail').showModal();
    if(setHash) { const url = new URL(location.href);url.hash = 'project=' + p.id;history.replaceState({},'',url); }
  }
  function handleHash() { const id = new URLSearchParams(location.hash.slice(1)).get('project'); if (id && projects.some(p => p.id === id)) showDetail(id,false); else if ($('#detail').open) $('#detail').close(); }
  async function copyLink(id) {
    const url = new URL(location.href); url.search = ''; url.hash = 'project=' + id;
    try { await navigator.clipboard.writeText(url.href); notify('Project link copied.'); } catch { notify('Copy the project link from your browser’s address bar.'); }
  }
  document.addEventListener('click', event => {
    const button = event.target.closest('button'); if(!button) return;
    if(button.dataset.view) changeView(button.dataset.view);
    else if(button.dataset.category) { state.category = state.category === button.dataset.category ? '' : button.dataset.category; update(true); }
    else if(button.dataset.platform) { state.platform = state.platform === button.dataset.platform ? '' : button.dataset.platform; update(true); }
    else if(button.dataset.tag) { state.tag = state.tag === button.dataset.tag ? '' : button.dataset.tag; update(true); }
    else if(button.dataset.clear) { state[button.dataset.clear] = ''; update(true); }
    else if(button.dataset.save) save(button.dataset.save);
    else if(button.dataset.detail) showDetail(button.dataset.detail);
    else if(button.hasAttribute('data-close')) button.closest('dialog').close();
    else if(button.dataset.copy) copyLink(button.dataset.copy);
  });
  $('#search').addEventListener('input',() => { clearTimeout(searchTimer);searchTimer=setTimeout(() => { state.q = $('#search').value.trim(); update(); },100); });
  $('#sort').addEventListener('change',() => { state.sort = $('#sort').value; update(); });
  $('#method').addEventListener('change',() => { state.method = $('#method').value; update(true); });
  $('#mobile-category').addEventListener('change',() => { state.category = $('#mobile-category').value; update(true); });
  $('#mobile-platform').addEventListener('change',() => { state.platform = $('#mobile-platform').value; update(true); });
  $('#reset').addEventListener('click',reset); $('#empty-reset').addEventListener('click',reset);
  for(const id of ['about-button','policy-button']) $('#' + id).addEventListener('click',() => $('#about').showModal());
  $('#detail').addEventListener('close',() => { const url = new URL(location.href);if(url.hash.startsWith('#project=')){url.hash='';history.replaceState({},'',url);} });
  for(const dialog of document.querySelectorAll('dialog')) dialog.addEventListener('click',event => { if(event.target === dialog){ const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close(); } });
  document.addEventListener('keydown',event => { if(event.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) && !document.querySelector('dialog[open]')){ event.preventDefault();$('#search').focus(); } });
  window.addEventListener('popstate',() => { readRoute();render();handleHash(); });
  window.addEventListener('hashchange',handleHash);
  window.addEventListener('storage',event => { if(event.key === 'slopforge-library'){try{const values=JSON.parse(event.newValue||'[]');favorites=new Set(Array.isArray(values)?values.filter(id=>projects.some(p=>p.id===id)):[]);render();}catch{}} });
  async function init() {
    try {
      const response = await fetch('projects.json'); if(!response.ok) throw new Error('Catalog response ' + response.status);
      const catalog = await response.json(); projects = catalog.projects;
      if(!Array.isArray(projects) || !projects.every(p => /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(p.repo) && /^[a-z0-9-]+$/.test(p.id))) throw new Error('Invalid catalog');
      favorites = new Set([...favorites].filter(id => projects.some(p => p.id === id)));
      $('#total-count').textContent = projects.length; $('#game-count').textContent = projects.filter(p => p.kind === 'games').length; $('#tool-count').textContent = projects.filter(p => p.kind === 'tools').length;
      readRoute(); render(); handleHash();
    } catch(error) {
      $('#result-count').textContent = 'Catalog unavailable';$('#empty').hidden = false;$('#empty-title').textContent = 'The forge couldn’t load its catalog.';$('#empty-copy').textContent = 'Refresh the page, or browse the complete catalog on GitHub.';$('#empty-reset').hidden = true;$('#shelves').innerHTML = `<a class="button primary" href="${repoRoot}/blob/main/CATALOG.md">Browse the GitHub catalog ↗</a>`;console.error(error);
    }
  }
  init();
})();
