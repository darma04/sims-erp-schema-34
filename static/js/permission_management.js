

(function() {
    'use strict';  

    
    document.addEventListener('DOMContentLoaded', function() {
        initializeAddPermissionModal();    
        initializeEditPermissionModal();   
    });

    
    function initializeAddPermissionModal() {
        
        const form = document.getElementById('addPermissionForm');
        if (!form) return;  

        
        form.addEventListener('submit', function(e) {
            e.preventDefault();                         
            handleAddPermissionSubmission(form);        
        });
    }

    
    function handleAddPermissionSubmission(form) {
        
        
        const formData = new FormData(form);
        const submitBtn = form.querySelector('button[type="submit"]');
        const originalBtnText = submitBtn.innerHTML;  

        
        const role = formData.get('role');       
        const module = formData.get('module');   

        if (!role || !module) {
            
            Swal.fire('Error', 'Silakan pilih Role dan Modul', 'error');
            return;  
        }

        
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Creating...';

        
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

        
        fetch('/access/permissions/ajax/create/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,    
            },
            body: formData                    
        })
        .then(response => response.json())     
        .then(data => {
            if (data.success) {
                
                
                showToast('success', data.message || 'Permission berhasil ditambahkan!');

                
                const modalInstance = bootstrap.Modal.getInstance(document.getElementById('addPermissionModal'));
                modalInstance.hide();

                
                setTimeout(() => location.reload(), 1000);
            } else {
                
                
                showToast('error', data.message || 'Gagal menambahkan permission');
                
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalBtnText;
            }
        })
        .catch(error => {
            
            
            console.error('Error:', error);
            showToast('error', 'Terjadi kesalahan saat menambahkan permission');
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnText;
        });
    }

    
    function initializeEditPermissionModal() {
        const modal = document.getElementById('editPermissionModal');
        const form = document.getElementById('editPermissionForm');

        if (!modal || !form) return;  

        
        modal.addEventListener('show.bs.modal', function(event) {
            const button = event.relatedTarget;  
            if (button) {
                
                const permissionId = button.getAttribute('data-permission-id');
                if (permissionId) {
                    loadPermissionData(permissionId);  
                }
            }
        });

        
        form.addEventListener('submit', function(e) {
            e.preventDefault();                        
            handleEditPermissionSubmission(form);       
        });
    }

    
    function loadPermissionData(permissionId) {
        
        const permissionIdInput = document.getElementById('editPermissionId');
        const roleDisplay = document.getElementById('editPermissionRoleDisplay');
        const moduleDisplay = document.getElementById('editPermissionModuleDisplay');

        
        if (roleDisplay) roleDisplay.textContent = 'Loading...';
        if (moduleDisplay) moduleDisplay.textContent = 'Loading...';

        
        fetch(`/access/permissions/ajax/${permissionId}/data/`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const permission = data.permission;

                    
                    if (permissionIdInput) permissionIdInput.value = permission.id;
                    
                    if (roleDisplay) roleDisplay.textContent = permission.role_display;
                    
                    if (moduleDisplay) moduleDisplay.textContent = permission.module_display;

                    
                    const viewCheck = document.getElementById('editCanView');
                    const createCheck = document.getElementById('editCanCreate');
                    const editCheck = document.getElementById('editCanEdit');
                    const deleteCheck = document.getElementById('editCanDelete');
                    const descInput = document.getElementById('editPermissionDescription');

                    
                    if (viewCheck) viewCheck.checked = permission.can_view;
                    if (createCheck) createCheck.checked = permission.can_create;
                    if (editCheck) editCheck.checked = permission.can_edit;
                    if (deleteCheck) deleteCheck.checked = permission.can_delete;
                    
                    if (descInput) descInput.value = permission.description || '';
                } else {
                    showToast('error', data.message || 'Gagal memuat data permission');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showToast('error', 'Terjadi kesalahan saat memuat permission');
            });
    }

    
    function handleEditPermissionSubmission(form) {
        const formData = new FormData(form);
        const permissionId = document.getElementById('editPermissionId').value;
        const submitBtn = form.querySelector('button[type="submit"]');
        const originalBtnText = submitBtn.innerHTML;

        
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Updating...';

        
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

        
        fetch(`/access/permissions/ajax/${permissionId}/edit/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
            },
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                
                showToast('success', data.message || 'Permission berhasil diupdate!');
                const modalInstance = bootstrap.Modal.getInstance(document.getElementById('editPermissionModal'));
                modalInstance.hide();
                setTimeout(() => location.reload(), 1000);
            } else {
                
                showToast('error', data.message || 'Gagal mengupdate permission');
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalBtnText;
            }
        })
        .catch(error => {
            
            console.error('Error:', error);
            showToast('error', 'Terjadi kesalahan saat mengupdate permission');
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnText;
        });
    }

    
    function showToast(type, message) {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                icon: type === 'success' ? 'success' : 'error',  
                title: type === 'success' ? 'Sukses!' : 'Error!', 
                text: message,                                      
                timer: 3000,                                        
                showConfirmButton: false,                           
                toast: true,                                        
                position: 'top-end'                                 
            });
        } else {
            
            alert(message);
        }
    }

})();  
