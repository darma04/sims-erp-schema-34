

(function() {
    'use strict';  

    
    document.addEventListener('DOMContentLoaded', function() {

        
        document.addEventListener('change', function(e) {
            
            if (e.target && e.target.id === 'selectAll') {
                handleSelectAllChange(e.target);
            }
            
            
            if (e.target && e.target.classList.contains('permission-checkbox')) {
                updateSelectAllState();
            }
        });

        
        document.addEventListener('submit', function(e) {
            if (e.target && e.target.id === 'addRoleForm') {
                e.preventDefault();                          
                handleAddRoleSubmission(e.target);           
            }
        });

        
        const addRoleModal = document.getElementById('addRoleModal');
        if (addRoleModal) {
            addRoleModal.addEventListener('hidden.bs.modal', function() {
                const form = document.getElementById('addRoleForm');
                if (form) {
                    form.reset();  
                    
                    const selectAll = document.getElementById('selectAll');
                    if (selectAll) selectAll.checked = false;
                }
            });
        }
    });

    
    function handleSelectAllChange(selectAllCheckbox) {
        const isChecked = selectAllCheckbox.checked;  
        const form = document.getElementById('addRoleForm');
        if (!form) return;

        
        const checkboxes = form.querySelectorAll('.permission-checkbox');
        
        checkboxes.forEach(function(checkbox) {
            checkbox.checked = isChecked;
        });
    }

    
    function updateSelectAllState() {
        const selectAllCheckbox = document.getElementById('selectAll');
        if (!selectAllCheckbox) return;

        
        const allCheckboxes = document.querySelectorAll('#addRoleForm .permission-checkbox');
        const checkedCheckboxes = document.querySelectorAll('#addRoleForm .permission-checkbox:checked');

        if (allCheckboxes.length === 0) return;

        
        selectAllCheckbox.checked = allCheckboxes.length === checkedCheckboxes.length;
        selectAllCheckbox.indeterminate = checkedCheckboxes.length > 0 && checkedCheckboxes.length < allCheckboxes.length;
    }

    
    function handleAddRoleSubmission(form) {
        
        const roleNameInput = document.getElementById('role_name');
        const roleName = roleNameInput ? roleNameInput.value.trim() : '';
        const submitBtn = form.querySelector('button[type="submit"]');

        
        if (!roleName) {
            showToast('error', 'Nama role harus diisi!');
            return;
        }

        if (!submitBtn) return;

        
        const originalBtnText = submitBtn.innerHTML;

        
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Menyimpan...';

        
        const csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
        const csrfToken = csrfInput ? csrfInput.value : '';

        
        const data = new URLSearchParams();
        data.append('role_name', roleName);
        data.append('csrfmiddlewaretoken', csrfToken);

        
        const moduleCheckboxes = form.querySelectorAll('.module-perm:checked');
        moduleCheckboxes.forEach(function(checkbox) {
            if (checkbox.name) {
                data.append(checkbox.name, 'on');  
            }
        });

        
        const subCheckboxes = form.querySelectorAll('.sub-perm:checked');
        subCheckboxes.forEach(function(checkbox) {
            if (checkbox.name) {
                data.append(checkbox.name, 'on');
            }
        });

        
        fetch('/access/roles/ajax/create/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',  
                'X-CSRFToken': csrfToken,                              
            },
            body: data.toString()  
        })
        .then(function(response) {
            return response.json();  
        })
        .then(function(responseData) {
            if (responseData.success) {
                
                showToast('success', responseData.message || 'Role berhasil ditambahkan!');

                
                var modalEl = document.getElementById('addRoleModal');
                var modal = bootstrap.Modal.getInstance(modalEl);
                if (modal) modal.hide();

                
                setTimeout(function() {
                    window.location.reload();
                }, 1000);
            } else {
                
                showToast('error', responseData.message || 'Gagal menambahkan role!');
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalBtnText;
            }
        })
        .catch(function(error) {
            
            console.error('Error:', error);
            showToast('error', 'Terjadi kesalahan pada server!');
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
