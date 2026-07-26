(() => {
  const badge=document.querySelector("#onlineOrderBadge");if(!badge)return;let latest=Number(sessionStorage.getItem("onlineLatestOrder")||0),muted=localStorage.getItem("onlineOrderMuted")==="1";
  function beep(){if(muted)return;try{const ctx=new AudioContext(),osc=ctx.createOscillator(),gain=ctx.createGain();osc.connect(gain);gain.connect(ctx.destination);gain.gain.value=.05;osc.frequency.value=880;osc.start();osc.stop(ctx.currentTime+.15)}catch{}}
  async function poll(){try{const response=await fetch("/online-orders/api/summary"),data=await response.json();badge.textContent=data.new_count||0;badge.hidden=!data.new_count;if(data.latest_id>latest&&latest)beep();latest=Math.max(latest,data.latest_id||0);sessionStorage.setItem("onlineLatestOrder",latest)}catch{}}
  document.querySelector("#muteOnlineAlerts")?.addEventListener("click",e=>{muted=!muted;localStorage.setItem("onlineOrderMuted",muted?"1":"0");e.currentTarget.textContent=muted?"เปิดเสียงแจ้งเตือน":"ปิดเสียงแจ้งเตือน"});poll();setInterval(poll,15000);
})();
