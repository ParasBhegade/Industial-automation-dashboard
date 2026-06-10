/* =========================================================
   SIMPLE LIGHT / DARK TOGGLE SYSTEM
   Saves theme in localStorage
   ========================================================= */

document.addEventListener("DOMContentLoaded", () => {
  const root = document.documentElement;
  const toggleBtn = document.querySelector(".theme-toggle");
  const STORAGE_KEY = "dashboard_theme_mode";

  // Apply saved theme
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved === "dark") {
    root.classList.add("dark");
    if (toggleBtn) toggleBtn.textContent = "☀️";
  } else {
    root.classList.remove("dark");
    if (toggleBtn) toggleBtn.textContent = "🌙";
  }

  // Toggle theme
  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      const isDark = root.classList.toggle("dark");
      localStorage.setItem(STORAGE_KEY, isDark ? "dark" : "light");
      toggleBtn.textContent = isDark ? "☀️" : "🌙";
    });
  }
});
