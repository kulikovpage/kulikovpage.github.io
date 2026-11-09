// Small helpers for every page: the year, fade-in on scroll, the screenshot arrows. Languages: lang.js.
(function () {
  var root = document.documentElement;

  document.addEventListener("DOMContentLoaded", function () {
    var year = document.querySelector("[data-year]");
    if (year) year.textContent = new Date().getFullYear();

    // What is on screen at load shows at once; the rest fades in on scroll. A timer reveals everything anyway,
    // so the text never stays hidden in a browser that throttles observers (background tabs, old devices).
    var items = Array.prototype.filter.call(document.querySelectorAll(".reveal"), function (el) {
      if (el.getBoundingClientRect().top < window.innerHeight) { el.classList.add("in"); return false; }
      return true;
    });
    setTimeout(function () { items.forEach(function (el) { el.classList.add("in"); }); }, 4000);
    if ("IntersectionObserver" in window) {
      var seen = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) { entry.target.classList.add("in"); seen.unobserve(entry.target); }
        });
      }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
      items.forEach(function (el, n) { el.style.transitionDelay = Math.min(n % 4, 3) * 60 + "ms"; seen.observe(el); });
    } else {
      items.forEach(function (el) { el.classList.add("in"); });
    }

    // Close the language menu when tapping elsewhere.
    document.addEventListener("click", function (event) {
      document.querySelectorAll("details.lang-menu[open]").forEach(function (menu) {
        if (!menu.contains(event.target)) menu.open = false;
      });
    });

    var track = document.querySelector(".shots-track");
    var buttons = document.querySelectorAll("[data-shots]");
    if (track && buttons.length) {
      var update = function () {
        var max = track.scrollWidth - track.clientWidth - 2;
        buttons[0].disabled = track.scrollLeft <= 2;
        buttons[1].disabled = track.scrollLeft >= max;
        var nav = buttons[0].parentElement;
        nav.hidden = max <= 0;
      };
      buttons.forEach(function (button) {
        button.addEventListener("click", function () {
          var item = track.querySelector("li");
          var step = item ? item.getBoundingClientRect().width + 16 : 280;
          track.scrollBy({ left: Number(button.dataset.shots) * step * 2, behavior: "smooth" });
        });
      });
      track.addEventListener("scroll", update, { passive: true });
      window.addEventListener("resize", update);
      update();
    }
  });
})();
