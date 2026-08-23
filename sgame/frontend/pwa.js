if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // The portal remains fully usable in a normal browser tab if registration fails.
    });
  });
}
