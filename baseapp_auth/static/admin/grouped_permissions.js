(function () {
    function updateParentCheckbox(parentCheckbox, childCheckboxes) {
      const allChecked = [...childCheckboxes].every(cb => cb.checked);
      const someChecked = [...childCheckboxes].some(cb => cb.checked);
  
      parentCheckbox.checked = allChecked;
      parentCheckbox.indeterminate = !allChecked && someChecked;
    }
  
    document.addEventListener('DOMContentLoaded', function () {
  
      document.querySelectorAll('.permission-model').forEach(modelBlock => {
        const modelSelectAll = modelBlock.querySelector('.select-all-model');
        const permissions = modelBlock.querySelectorAll('.permission-checkbox');
  
        // Model → permissions
        modelSelectAll.addEventListener('change', () => {
          permissions.forEach(cb => cb.checked = modelSelectAll.checked);
        });
  
        // Permissions → model
        permissions.forEach(cb => {
          cb.addEventListener('change', () => {
            updateParentCheckbox(modelSelectAll, permissions);
          });
        });
  
        updateParentCheckbox(modelSelectAll, permissions);
      });
  
      document.querySelectorAll('.permission-app').forEach(appBlock => {
        const appSelectAll = appBlock.querySelector('.select-all-app');
        const appPermissions = appBlock.querySelectorAll('.permission-checkbox');
  
        // App → all permissions
        appSelectAll.addEventListener('change', () => {
          appPermissions.forEach(cb => cb.checked = appSelectAll.checked);
        });
  
        // Any permission change → app
        appPermissions.forEach(cb => {
          cb.addEventListener('change', () => {
            updateParentCheckbox(appSelectAll, appPermissions);
          });
        });
  
        updateParentCheckbox(appSelectAll, appPermissions);
      });
  
    });
  })();
  