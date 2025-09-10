async function updateNotifications() {
  try {
    fetch('/api/notifications')
    .then(res => res.json())
    .then(data => {
      const countEl = document.getElementById('notif-count');
      if (countEl) countEl.textContent = data.count;
    });
  } 
  catch (e) { 
    console.error(e); }
}

async function updateSignalBars() {
  try {
    const res = await fetch('/api/signal-strength');
    const { strength } = await res.json();
    const bars = document.querySelectorAll('#signal-bars .bar');
    bars.forEach((bar, i) => {
      bar.classList.toggle('active', i < strength);
    });
  } catch(e) { console.error(e); }
}

// initial call
updateNotifications();
updateSignalBars();

// intervals
setInterval(updateNotifications, 5000);
setInterval(updateSignalBars, 1000);
