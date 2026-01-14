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

  function initSelectAllControls() {
    /* ---------- MODEL LEVEL ---------- */
    document.querySelectorAll(".permission-model").forEach(modelBlock => {
      const modelToggle = modelBlock.querySelector(".select-all-model");
      const permissions = modelBlock.querySelectorAll(".permission-checkbox");

      if (!modelToggle) return;

      modelToggle.addEventListener("change", () => {
        permissions.forEach(cb => cb.checked = modelToggle.checked);

        // Update app after model change
        const appBlock = modelBlock.closest(".permission-app");
        if (!appBlock) return;

        const appToggle = appBlock.querySelector(".select-all-app");
        const allPermissions = appBlock.querySelectorAll(".permission-checkbox");

        if (appToggle) {
          updateParent(appToggle, allPermissions);
        }
      });

      updateParent(modelToggle, permissions);
    });

    /* ---------- APP LEVEL ---------- */
    document.querySelectorAll(".permission-app").forEach(appBlock => {
      const appToggle = appBlock.querySelector(".select-all-app");
      const modelBlocks = appBlock.querySelectorAll(".permission-model");
      const allPermissions = appBlock.querySelectorAll(".permission-checkbox");

      if (!appToggle) return;

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

      updateParent(appToggle, allPermissions);
    });
  }

  function initPermissionDelegation() {
    document.addEventListener("change", event => {
      const checkbox = event.target;
      if (!checkbox.classList.contains("permission-checkbox")) return;

      const modelBlock = checkbox.closest(".permission-model");
      const appBlock = checkbox.closest(".permission-app");

      if (modelBlock) {
        const modelToggle = modelBlock.querySelector(".select-all-model");
        const perms = modelBlock.querySelectorAll(".permission-checkbox");
        if (modelToggle) {
          updateParent(modelToggle, perms);
        }
      }

      if (appBlock) {
        const appToggle = appBlock.querySelector(".select-all-app");
        const allPermissions = appBlock.querySelectorAll(".permission-checkbox");
        if (appToggle) {
          updateParent(appToggle, allPermissions);
        }
      }
    });
  }

  function initFiltering() {
    const filterInput = document.querySelector(".permission-filter");
    if (!filterInput) return;
  
    filterInput.addEventListener("input", () => {
      const query = filterInput.value.toLowerCase();
  
      // Filter individual permissions
      document.querySelectorAll(".permission-label").forEach(label => {
        const text = label.textContent.toLowerCase();
        const li = label.closest("li");
  
        if (!li) return;
  
        li.classList.toggle(
          "is-hidden",
          !text.includes(query)
        );
      });
  
      // Hide empty models
      document.querySelectorAll(".permission-model").forEach(model => {
        const hasVisiblePerms =
          model.querySelectorAll("li:not(.is-hidden)").length > 0;
  
        model.classList.toggle("is-hidden", !hasVisiblePerms);
      });
  
      // Hide empty apps
      document.querySelectorAll(".permission-app").forEach(app => {
        const hasVisibleModels =
          app.querySelectorAll(
            ".permission-model:not(.is-hidden)"
          ).length > 0;
  
        app.classList.toggle("is-hidden", !hasVisibleModels);
      });
    });
  }  

  document.addEventListener("DOMContentLoaded", () => {
    initSelectAllControls();
    initPermissionDelegation();
    initFiltering();
  });

})();
