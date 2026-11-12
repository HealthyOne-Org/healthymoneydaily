/* Healthy Money Daily: nav toggle, reveal-on-scroll, sticky Budget Shield bar, App Store click tracking (PostHog 458884). */
(function(){
  var SITE='healthymoneydaily';
  var nav=document.querySelector('.nav'),t=document.querySelector('.nav-toggle');
  if(t&&nav){t.addEventListener('click',function(){nav.classList.toggle('open');t.setAttribute('aria-expanded',nav.classList.contains('open'))});}

  // Gentle fade-in as sections scroll into view. CSS only hides [data-reveal] when <html> has .js.
  window.__hmdReady=true;
  var els=document.querySelectorAll('[data-reveal]');
  if('IntersectionObserver' in window){
    var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}})},{rootMargin:'0px 0px -8% 0px',threshold:.08});
    els.forEach(function(el){io.observe(el)});
  }else{els.forEach(function(el){el.classList.add('in')})}

  function cap(ev,props){try{if(window.posthog&&posthog.capture){posthog.capture(ev,props)}}catch(e){}}

  // Every App Store link carries data-placement; its ct token says the same thing in App Store Connect.
  document.addEventListener('click',function(e){
    var a=e.target.closest&&e.target.closest('a');if(!a)return;
    var href=a.getAttribute('href')||'';
    if(href.indexOf('apps.apple.com')<0)return;
    var placement=a.getAttribute('data-placement')||'inline';
    cap('blog_download_cta_click',{site:SITE,placement:placement,store:'ios',app:'budget_shield',path:location.pathname});
  },true);

  // Sticky bar (posts only): hidden for 7 days after the reader closes it.
  var K='hmd_bar_closed',bar=document.getElementById('hmd-sticky');
  if(bar){
    var until=0;try{until=parseInt(localStorage.getItem(K)||'0',10)}catch(e){}
    if(Date.now()>until){bar.hidden=false;document.body.classList.add('has-sticky')}
    var c=document.getElementById('hmd-sticky-close');
    if(c){c.addEventListener('click',function(){bar.hidden=true;document.body.classList.remove('has-sticky');
      try{localStorage.setItem(K,String(Date.now()+7*864e5))}catch(e){}
      cap('blog_download_cta_click',{site:SITE,placement:'sticky_dismiss',store:'',app:'budget_shield',path:location.pathname});});}
  }
})();
