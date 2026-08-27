

(function() {
    'use strict';  

    
    let checkboxesRendered = false;

    
    let currentRoleCode = null;

    
    document.addEventListener('DOMContentLoaded', function() {
        const modal = document.getElementById('editRoleModal');
        const form = document.getElementById('editRoleForm');

        if (!modal || !form) return;  

        
        modal.addEventListener('show.bs.modal', function(event) {
            var button = event.relatedTarget;  

            if (button) {
                
                
                var roleCode = button.getAttribute('data-role-code');
                if (roleCode) {
                    console.log('[EditRole] Loading data for role:', roleCode);
                    loadRoleDataForEdit(roleCode);  
                }
            }
        });

        
        modal.addEventListener('hidden.bs.modal', function() {
            currentRoleCode = null;
            
            
        });

        
        form.addEventListener('submit', function(e) {
            e.preventDefault();        
            submitEditRole(form);      
        });
    });

    
    function loadRoleDataForEdit(roleCode) {
        
        const roleCodeInput = document.getElementById('editRoleCode');
        const roleNameInput = document.getElementById('editRoleName');
        const container = document.getElementById('editPermissionCheckboxContainer');

        if (!roleCodeInput) return;

        // Simpan role code ke input hidden
        roleCodeInput.value = roleCode;
        currentRoleCode = roleCode;

        // SELALU clear container dan re-render saat role baru dibuka
        if (container) {
            container.innerHTML = '<div class="text-center py-4"><span class="spinner-border spinner-border-sm me-2"></span>Memuat permissions...</div>';
        }

        // Reset guard render agar renderPermissionCheckboxes bisa jalan ulang
        if (typeof _renderedContainers !== 'undefined') {
            delete _renderedContainers['editPermissionCheckboxContainer_edit'];
        }

        // Fetch data permissions dari server
        fetch(`/access/roles/ajax/${roleCode}/data/`)
            .then(response => response.json())
            .then(data => {
                console.log('[EditRole] Data loaded:', data);

                if (data.success) {
                    // Set nama role di input
                    if (roleNameInput) {
                        roleNameInput.value = data.role_display || roleCode.replace(/_/g, ' ');
                    }

                    // Render checkbox (container sudah dikosongkan di atas)
                    if (container) container.innerHTML = '';
                    if (typeof renderPermissionCheckboxes === 'function') {
                        renderPermissionCheckboxes('editPermissionCheckboxContainer', 'edit');
                    }

                    // Populate checkbox berdasarkan data permissions
                    requestAnimationFrame(function() {
                        populatePermissionCheckboxes(data.permissions || []);
                    });
                } else {
                    showAlert('error', data.message || 'Gagal memuat data role');
                    if (container) {
                        container.innerHTML = '<div class="alert alert-danger">Gagal memuat data permission</div>';
                    }
                }
            })
            .catch(error => {
                console.error('[EditRole] Error loading role data:', error);
                showAlert('error', 'Gagal memuat data role dari server');
                if (container) {
                    container.innerHTML = '<div class="alert alert-danger">Gagal memuat data permission</div>';
                }
            });
    }

    
    function populatePermissionCheckboxes(permissions) {
        if (!Array.isArray(permissions)) return;

        // Reset semua checkbox dulu
        document.querySelectorAll('#editRoleForm input[type="checkbox"]').forEach(cb => {
            cb.checked = false;
        });

        // Populate berdasarkan data permissions dari server
        permissions.forEach(perm => {
            const module = perm.module;
            const subModule = perm.sub_module;

            if (subModule) {
                // Sub-module: HANYA centang can_view (1 checkbox saja)
                // Create/Edit/Delete sub-menu diwakili oleh checkbox menu utama
                if (perm.can_view) {
                    const cb = document.getElementById(`edit_${module}_${subModule}_view`);
                    if (cb) cb.checked = true;
                }
            } else {
                // Module-level: centang sesuai masing-masing flag
                const idPrefix = `edit_${module}_`;
                const actions = ['view', 'create', 'edit', 'delete'];

                actions.forEach(action => {
                    const fieldName = action === 'view' ? 'can_view' :
                                      action === 'create' ? 'can_create' :
                                      action === 'edit' ? 'can_edit' : 'can_delete';
                    if (perm[fieldName]) {
                        const cb = document.getElementById(`${idPrefix}${action}`);
                        if (cb) cb.checked = true;
                    }
                });
            }
        });

        console.log(`[EditRole] Populated ${permissions.length} permission records`);
    }

    
    function submitEditRole(form) {
        
        const formData = new FormData(form);
        const roleCode = document.getElementById('editRoleCode').value;
        const submitBtn = form.querySelector('button[type="submit"]');
        const originalBtnText = submitBtn.innerHTML;

        
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Menyimpan...';

        
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

        
        fetch(`/access/roles/ajax/${roleCode}/update/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,  
            },
            body: formData  
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                
                showAlert('success', data.message || 'Permissions berhasil diupdate!');

                
                const modalEl = document.getElementById('editRoleModal');
                const modalInstance = bootstrap.Modal.getInstance(modalEl);
                if (modalInstance) modalInstance.hide();

                
                setTimeout(() => location.reload(), 1500);
            } else {
                
                showAlert('error', data.message || 'Gagal mengupdate permissions');
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalBtnText;
            }
        })
        .catch(error => {
            
            console.error('[EditRole] Error saving role:', error);
            showAlert('error', 'Terjadi kesalahan saat menyimpan. Coba lagi.');
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnText;
        });
    }

    
    function showAlert(type, message) {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                icon: type === 'success' ? 'success' : 'error',
                title: type === 'success' ? 'Berhasil!' : 'Error!',
                text: message,
                timer: type === 'success' ? 2000 : undefined,       
                showConfirmButton: type !== 'success'                 
            });
        } else {
            
            alert(message);
        }
    }

})();  
