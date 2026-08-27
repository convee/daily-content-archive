(() => {
  const root = document.documentElement;
  const themeButton = document.querySelector('.theme-toggle');
  const themes = ['auto', 'light', 'dark'];

  const savedTheme = (() => {
    try { return localStorage.getItem('archive-theme'); } catch (_) { return null; }
  })();
  if (themes.includes(savedTheme)) root.dataset.theme = savedTheme;

  const updateThemeLabel = () => {
    if (!themeButton) return;
    const names = { auto: '跟随系统', light: '浅色', dark: '深色' };
    const current = root.dataset.theme || 'auto';
    themeButton.title = `当前：${names[current]}；点击切换`;
    themeButton.setAttribute('aria-label', themeButton.title);
  };
  updateThemeLabel();
  themeButton?.addEventListener('click', () => {
    const current = root.dataset.theme || 'auto';
    const next = themes[(themes.indexOf(current) + 1) % themes.length];
    root.dataset.theme = next;
    try { localStorage.setItem('archive-theme', next); } catch (_) { /* storage may be unavailable */ }
    updateThemeLabel();
  });

  const cards = [...document.querySelectorAll('.archive-card')];
  const historyEntries = [...document.querySelectorAll('[data-archive-entry]')];
  const historyGroups = [...document.querySelectorAll('[data-history-group]')];
  const search = document.querySelector('.archive-search');
  const clearSearch = document.querySelector('.clear-search');
  const filterButtons = [...document.querySelectorAll('.filter-button')];
  const resultsSummary = document.querySelector('.results-summary');
  const emptyState = document.querySelector('.empty-state');
  let activePlatform = 'all';

  const normalize = value => value.toLocaleLowerCase('zh-CN').trim();
  const filterCards = () => {
    if (!cards.length) return;
    const query = normalize(search?.value || '');
    let visibleCards = 0;
    cards.forEach(card => {
      const platformMatch = activePlatform === 'all' || card.dataset.platform === activePlatform;
      const searchMatch = !query || normalize(card.dataset.search || card.textContent).includes(query);
      card.hidden = !(platformMatch && searchMatch);
      if (!card.hidden) visibleCards += 1;
    });
    let visibleHistory = 0;
    historyEntries.forEach(entry => {
      const platformMatch = activePlatform === 'all' || entry.dataset.platform === activePlatform;
      const searchMatch = !query || normalize(entry.dataset.search || entry.textContent).includes(query);
      entry.hidden = !(platformMatch && searchMatch);
      if (!entry.hidden) visibleHistory += 1;
    });
    historyGroups.forEach(group => {
      const matchingEntries = [...group.querySelectorAll('[data-archive-entry]:not([hidden])')];
      group.hidden = matchingEntries.length === 0;
      const count = group.querySelector('[data-history-count]');
      if (count) count.textContent = `${matchingEntries.length} 篇`;
      if (query && matchingEntries.length) group.open = true;
    });
    if (resultsSummary) resultsSummary.textContent = `显示 ${visibleCards} 个最新入口 · ${visibleHistory} 篇历史简报`;
    if (emptyState) emptyState.dataset.visible = String(visibleCards + visibleHistory === 0);
    if (clearSearch) clearSearch.dataset.visible = String(Boolean(query));
  };

  search?.addEventListener('input', filterCards);
  clearSearch?.addEventListener('click', () => {
    search.value = '';
    search.focus();
    filterCards();
  });
  filterButtons.forEach(button => button.addEventListener('click', () => {
    activePlatform = button.dataset.filter;
    filterButtons.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    filterCards();
  }));
  filterCards();

  const article = document.querySelector('[data-article]');
  const toc = document.querySelector('#page-toc');
  const tocPanel = document.querySelector('.toc-panel');
  const tocToggle = document.querySelector('.toc-title');
  const headings = article ? [...article.querySelectorAll('h2, h3')] : [];
  const toast = document.createElement('div');
  toast.className = 'copy-toast';
  toast.setAttribute('role', 'status');
  toast.setAttribute('aria-live', 'polite');
  toast.textContent = '链接已复制';
  document.body.append(toast);
  let toastTimer;

  const showToast = text => {
    toast.textContent = text;
    toast.dataset.visible = 'true';
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.dataset.visible = 'false'; }, 1800);
  };

  headings.forEach((heading, index) => {
    if (!heading.id) heading.id = `section-${index + 1}`;
    const link = document.createElement('a');
    link.href = `#${heading.id}`;
    link.textContent = heading.textContent;
    link.dataset.level = heading.tagName.slice(1);
    toc?.append(link);

    const copyButton = document.createElement('button');
    copyButton.className = 'heading-anchor';
    copyButton.type = 'button';
    copyButton.setAttribute('aria-label', `复制“${heading.textContent}”的链接`);
    copyButton.title = '复制此节链接';
    copyButton.textContent = '#';
    copyButton.addEventListener('click', async () => {
      const url = `${location.origin}${location.pathname}#${heading.id}`;
      try {
        await navigator.clipboard.writeText(url);
        showToast('链接已复制');
      } catch (_) {
        location.hash = heading.id;
        showToast('已定位到本节');
      }
    });
    heading.append(copyButton);
  });

  if (tocPanel && !headings.length) tocPanel.hidden = true;
  tocToggle?.addEventListener('click', () => {
    const open = tocPanel.dataset.open !== 'true';
    tocPanel.dataset.open = String(open);
    tocToggle.setAttribute('aria-expanded', String(open));
  });

  if ('IntersectionObserver' in window && headings.length) {
    const tocLinks = [...toc.querySelectorAll('a')];
    const observer = new IntersectionObserver(entries => {
      const visibleHeading = entries.find(entry => entry.isIntersecting);
      if (!visibleHeading) return;
      tocLinks.forEach(link => link.setAttribute('aria-current', String(link.hash === `#${visibleHeading.target.id}`)));
    }, { rootMargin: '-18% 0px -68% 0px', threshold: 0 });
    headings.forEach(heading => observer.observe(heading));
  }

  const progressBar = document.querySelector('.reading-progress span');
  const backToTop = document.querySelector('.back-to-top');
  const updateScrollUi = () => {
    const max = document.documentElement.scrollHeight - window.innerHeight;
    const progress = max > 0 ? Math.min(100, (window.scrollY / max) * 100) : 0;
    if (progressBar) progressBar.style.width = `${progress}%`;
    if (backToTop) backToTop.dataset.visible = String(window.scrollY > 520);
  };
  addEventListener('scroll', updateScrollUi, { passive: true });
  updateScrollUi();
  backToTop?.addEventListener('click', () => scrollTo({ top: 0, behavior: 'smooth' }));
})();
