// Project pages exist in several languages. Loaded in <head> without defer, so the redirect happens before paint.
(function () {
  var root = document.documentElement;
  // The English page sends a visitor to their own language once,
  // unless they picked a language themselves. Old links like /peekaword/#ru land on the right page too.
  var langs = (root.dataset.langs || "").split(",").filter(Boolean);
  if (langs.length > 1) {
    var store = function (code) { try { localStorage.setItem("lang", code); } catch (e) {} };
    var stored = null;
    try { stored = localStorage.getItem("lang"); } catch (e) {}
    var go = function (code) {
      if (!code || code === root.dataset.lang || langs.indexOf(code) < 0) return false;
      location.replace(root.dataset.base + (code === "en" ? "" : code + "/") + (root.dataset.page ? root.dataset.page + "/" : ""));
      return true;
    };
    var hash = location.hash.slice(1);
    if (langs.indexOf(hash) >= 0) {
      store(hash);
      if (go(hash)) return;
    } else if (root.dataset.lang === "en") {
      var wanted = stored;
      if (!wanted) {
        var prefs = navigator.languages || [navigator.language || ""];
        for (var i = 0; i < prefs.length && !wanted; i++) {
          var code = String(prefs[i]).slice(0, 2).toLowerCase();
          if (code === "en") break;
          if (langs.indexOf(code) >= 0) wanted = code;
        }
      }
      if (go(wanted)) return;
    }
    document.addEventListener("click", function (event) {
      var link = event.target.closest && event.target.closest("[data-lang]");
      if (link && link.tagName === "A") store(link.dataset.lang);
    });
  }

})();
