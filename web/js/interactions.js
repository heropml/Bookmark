
function initPointerEffects() {
  let moveRaf = 0;
  const rootStyle = document.documentElement.style;
  document.addEventListener("pointermove", (e) => {
    if (document.documentElement.dataset.fx === "off") return;
    if (motionOk() && spawnTrail(e.clientX, e.clientY)) startSky();
    const x = e.clientX + "px";
    const y = e.clientY + "px";
    if (moveRaf) return;
    moveRaf = requestAnimationFrame(() => {
      moveRaf = 0;
      rootStyle.setProperty("--mx", x);
      rootStyle.setProperty("--my", y);
    });
  }, { passive: true });
  if (matchMedia("(hover: hover) and (pointer: fine)").matches) {
    const tiltPending = new Map();
    let tiltRaf = 0;
    const flushTilt = () => {
      tiltRaf = 0;
      for (const [card, ev] of tiltPending) {
        const r = card.getBoundingClientRect();
        const px = (ev.clientX - r.left) / r.width - 0.5;
        const py = (ev.clientY - r.top) / r.height - 0.5;
        card.classList.add("is-tilting");
        card.style.setProperty("--rx", (-py * 6.5).toFixed(2) + "deg");
        card.style.setProperty("--ry", (px * 8.5).toFixed(2) + "deg");
        card.style.setProperty("--gx", ((px + 0.5) * 100).toFixed(1) + "%");
        card.style.setProperty("--gy", ((py + 0.5) * 100).toFixed(1) + "%");
      }
      tiltPending.clear();
    };
    const mainEl = document.getElementById("main");
    mainEl.addEventListener("pointermove", (e) => {
      if (!motionOk()) return;
      const card = e.target.closest(".card");
      if (!card) return;
      tiltPending.set(card, e);
      if (!tiltRaf) tiltRaf = requestAnimationFrame(flushTilt);
    }, { passive: true });
    mainEl.addEventListener("pointerout", (e) => {
      const card = e.target.closest(".card");
      if (!card || card.contains(e.relatedTarget)) return;
      tiltPending.delete(card);
      card.classList.remove("is-tilting");
      card.style.setProperty("--rx", "0deg");
      card.style.setProperty("--ry", "0deg");
    }, { passive: true });
  }
}
