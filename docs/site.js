/* 사이트 공용 동작 — 좁은 화면의 ☰ 메뉴 열고 닫기, '맨 위로' 버튼.
   메뉴 자체는 HTML 에 있으므로 이 파일이 없어도 링크는 보이고 동작한다. */
(function(){
  var bar = document.getElementById('topbar');
  if (bar) {
    var btn = bar.querySelector('.burger');
    var setOpen = function(open){
      bar.classList.toggle('open', open);
      if (btn) { btn.setAttribute('aria-expanded', open ? 'true' : 'false'); btn.textContent = open ? '✕' : '☰'; }
    };
    if (btn) btn.addEventListener('click', function(){ setOpen(!bar.classList.contains('open')); });
    bar.querySelectorAll('.menu a').forEach(function(a){ a.addEventListener('click', function(){ setOpen(false); }); });
    document.addEventListener('keydown', function(e){ if (e.key === 'Escape') setOpen(false); });
    document.addEventListener('click', function(e){ if (!bar.contains(e.target)) setOpen(false); });
  }

  var top = document.createElement('button');
  top.id = 'toTop'; top.type = 'button'; top.title = '맨 위로'; top.setAttribute('aria-label', '맨 위로');
  top.textContent = '↑';
  top.addEventListener('click', function(){ window.scrollTo({top: 0, behavior: 'smooth'}); });
  document.body.appendChild(top);
  var onScroll = function(){ top.classList.toggle('show', window.scrollY > 500); };
  window.addEventListener('scroll', onScroll, {passive: true});
  onScroll();
})();
