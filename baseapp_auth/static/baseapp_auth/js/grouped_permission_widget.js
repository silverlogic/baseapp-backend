/**
 * JavaScript for grouped permission widget.
 * Handles:
 * - select-all behavior (app & model levels)
 * - hierarchical checkbox state sync
 * - permission filtering
 */

(function () {

  function updateParent(parent, children) {
    const all = [...children].every(c => c.checked);
    const some = [...children].some(c => c.checked);

    parent.checked = all;
    parent.indeterminate = !all && some;
  }

  function initModelLevel() {
    document.querySelectorAll(".permission-model").forEach(modelBlock => {
      const modelToggle = modelBlock.querySelector(".select-all-model");
      const permissions = modelBlock.querySelectorAll(".permission-checkbox");

      if (!modelToggle) return;

      // Model > permissions
      modelToggle.addEventListener("change", () => {
        permissions.forEach(cb => cb.checked = modelToggle.checked);

        // Model > app
        const appBlock = modelBlock.closest(".permission-app");
        if (!appBlock) return;

        const appToggle = appBlock.querySelector(".select-all-app");
        const allPermissions = appBlock.querySelectorAll(".permission-checkbox");

        if (appToggle) {
          updateParent(appToggle, allPermissions);
        }
      });

      // Permissions > model
      permissions.forEach(cb => {
        cb.addEventListener("change", () => {
          updateParent(modelToggle, permissions);
        });
      });

      // Initial state
      updateParent(modelToggle, permissions);
    });
  }

  function initAppLevel() {
    document.querySelectorAll(".permission-app").forEach(appBlock => {
      const appToggle = appBlock.querySelector(".select-all-app");
      const modelBlocks = appBlock.querySelectorAll(".permission-model");
      const allPermissions = appBlock.querySelectorAll(".permission-checkbox");

      if (!appToggle) return;

      // App > models + permissions
      appToggle.addEventListener("change", () => {
        allPermissions.forEach(cb => cb.checked = appToggle.checked);

        modelBlocks.forEach(modelBlock => {
          const modelToggle = modelBlock.querySelector(".select-all-model");
          const perms = modelBlock.querySelectorAll(".permission-checkbox");

          if (modelToggle) {
            updateParent(modelToggle, perms);
          }
        });
      });

      // Permissions > app
      allPermissions.forEach(cb => {
        cb.addEventListener("change", () => {
          updateParent(appToggle, allPermissions);
        });
      });

      // Initial state
      updateParent(appToggle, allPermissions);
    });
  }

  function initFiltering() {
    const filterInput = document.querySelector(".permission-filter");
    if (!filterInput) return;

    filterInput.addEventListener("input", () => {
      const query = filterInput.value.toLowerCase();

      document.querySelectorAll(".permission-label").forEach(label => {
        const text = label.textContent.toLowerCase();
        label.closest("li").style.display =
          text.includes(query) ? "" : "none";
      });

      // Hide empty models
      document.querySelectorAll(".permission-model").forEach(model => {
        const visible = model.querySelectorAll(
          'li:not([style*="display: none"])'
        ).length > 0;
        model.style.display = visible ? "" : "none";
      });

      // Hide empty apps
      document.querySelectorAll(".permission-app").forEach(app => {
        const visible = app.querySelectorAll(
          '.permission-model:not([style*="display: none"])'
        ).length > 0;
        app.style.display = visible ? "" : "none";
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initModelLevel();
    initAppLevel();
    initFiltering();
  });

})();
