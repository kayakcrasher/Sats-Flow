/* SatsFlow theme toggle.
 * Themes are defined in style.css via [data-theme="..."].
 * Choice persists in localStorage under "satsflow-theme".
 */
(function () {
    const STORAGE_KEY = "satsflow-theme";
    const THEMES = ["dark", "terminal"];
    const DEFAULT = "dark";

    function apply(theme) {
        if (!THEMES.includes(theme)) theme = DEFAULT;
        document.documentElement.setAttribute("data-theme", theme);
    }

    function current() {
        return document.documentElement.getAttribute("data-theme") || DEFAULT;
    }

    function next() {
        const i = THEMES.indexOf(current());
        return THEMES[(i + 1) % THEMES.length];
    }

    // Apply saved theme before paint to avoid a flash
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) apply(saved);

    document.addEventListener("DOMContentLoaded", function () {
        const btn = document.querySelector(".theme-toggle");
        if (!btn) return;

        btn.disabled = false;
        btn.removeAttribute("title");
        btn.setAttribute("aria-label", "Toggle theme");

        btn.addEventListener("click", function () {
            const t = next();
            apply(t);
            localStorage.setItem(STORAGE_KEY, t);
        });
    });
})();
