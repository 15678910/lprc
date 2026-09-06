/* 좌측 '화면 목차' — 측정기(index) 이외의 문서 페이지 공용.
   index 는 카드가 렌더마다 바뀌어 자기 sideNav 를 갖고 있고, 여기서는 정적 문서라
   페이지의 .card > h2 를 한 번 읽어 목차를 만든다. 스타일도 index 의 .sidenav 와 같은 값이다
   (한 곳에서 고치면 다른 곳도 고칠 것). 화면이 1240px 이상일 때만 보인다. */
(function(){
  var css = '.sidenav{display:none}'
    + '@media (min-width:1240px){body{padding-left:200px}'
    + '.sidenav{display:block;position:fixed;left:0;top:0;bottom:0;width:200px;z-index:50;'
    + 'background:#0d1219;border-right:1px solid var(--line);padding:16px 10px;overflow-y:auto}'
    + '.sidenav b{display:block;color:var(--mut);font-size:.82rem;letter-spacing:.02em;'
    + 'padding:0 10px 8px;border-bottom:1px solid var(--line);margin-bottom:8px}'
    + '.sidenav a{display:block;color:var(--mut);text-decoration:none;font-size:.92rem;line-height:1.35;'
    + 'padding:8px 10px;border-radius:8px;margin-bottom:2px;border-left:3px solid transparent}'
    + '.sidenav a:hover{color:var(--tx);background:rgba(88,166,255,.10)}'
    + '.sidenav a.on{color:var(--tx);background:rgba(88,166,255,.15);border-left-color:var(--acc);font-weight:600}'
    + '.sidenav .top{margin-top:10px;padding-top:8px;border-top:1px solid var(--line);font-size:.86rem}}'
    + '@media print{.sidenav{display:none}}';
  var st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);

  function build(){
    var cards = Array.prototype.slice.call(document.querySelectorAll('.card'))
      .filter(function(c){ return c.querySelector(':scope > h2'); });
    if (cards.length < 3) return;                       // 목차가 필요할 만큼 길지 않다
    var nav = document.createElement('nav');
    nav.className = 'sidenav noprint'; nav.id = 'snav'; nav.setAttribute('aria-label', '화면 목차');
    var h1 = document.querySelector('h1');
    nav.innerHTML = '<b>' + (h1 ? h1.textContent.trim() : '화면 목차') + '</b>';
    var links = cards.map(function(c, i){
      if (!c.id) c.id = 'sec' + i;
      var t = c.querySelector(':scope > h2').textContent.trim();
      // 부제(— 뒤)는 목차에서 뺀다. 한 줄에 들어와야 훑어진다.
      t = t.split('—')[0].trim();
      var a = document.createElement('a');
      a.href = '#' + c.id; a.textContent = (i + 1) + '. ' + t;
      a.addEventListener('click', function(e){
        e.preventDefault(); c.scrollIntoView({behavior: 'smooth', block: 'start'});
        history.replaceState(null, '', '#' + c.id);
      });
      nav.appendChild(a); return a;
    });
    var top = document.createElement('a'); top.className = 'top'; top.href = '#';
    top.textContent = '↑ 맨 위로';
    top.addEventListener('click', function(e){ e.preventDefault(); window.scrollTo({top: 0, behavior: 'smooth'}); });
    nav.appendChild(top);
    document.body.insertBefore(nav, document.body.firstChild);

    // 화면 위쪽 15~30% 구간에 걸친 카드를 '현재' 로 표시한다 (index 와 같은 규칙)
    if ('IntersectionObserver' in window) {
      var obs = new IntersectionObserver(function(es){
        es.forEach(function(en){
          if (!en.isIntersecting) return;
          var i = cards.indexOf(en.target);
          links.forEach(function(a, k){ a.classList.toggle('on', k === i); });
        });
      }, {rootMargin: '-15% 0px -70% 0px'});
      cards.forEach(function(c){ obs.observe(c); });
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', build);
  else build();
})();
