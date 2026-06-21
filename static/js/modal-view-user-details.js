

(function() {
    'use strict';  

    
    document.addEventListener('DOMContentLoaded', function() {
        initializeViewUserDetailsModal();
    });

    
    function initializeViewUserDetailsModal() {
        const modal = document.getElementById('viewUserDetailsModal');
        if (!modal) return;  

        
        modal.addEventListener('show.bs.modal', function(event) {
            const button = event.relatedTarget;  
            if (button) {
                
                
                const userId = button.getAttribute('data-user-id');
                if (userId) {
                    loadUserData(userId);  
                }
            }
        });
    }

    
    function loadUserData(userId) {
        console.log('Loading user data for ID:', userId);

        
        document.getElementById('viewUserFullName').textContent = 'Loading...';
        document.getElementById('viewUserUsername').textContent = '-';
        document.getElementById('viewUserEmail').textContent = '-';
        document.getElementById('viewUserPermissions').innerHTML = '<span class="badge bg-label-secondary">Loading...</span>';

        
        fetch(`/user-management/detail/${userId}/ajax/`)
            .then(response => {
                console.log('Response status:', response.status);
                if (!response.ok) {
                    
                    
                    populateFromDOM(userId);
                    return null;  
                }
                return response.json();  
            })
            .then(data => {
                if (data && data.success) {
                    
                    populateModal(data.user);
                } else if (data === null) {
                    
                    console.log('Populated from DOM data');
                } else {
                    
                    console.error('Failed to load user data:', data.message);
                    populateFromDOM(userId);
                }
            })
            .catch(error => {
                
                console.error('Error loading user data:', error);
                populateFromDOM(userId);  
            });
    }

    
    function populateFromDOM(userId) {
        console.log('Populating modal from DOM data');

        
        const userRow = document.querySelector(`tr[data-user-id="${userId}"]`) ||
                       document.querySelector(`a[data-user-id="${userId}"]`).closest('tr');

        if (userRow) {
            
            
            const cells = userRow.querySelectorAll('td');

            
            const username = cells[1]?.textContent.trim() || 'Unknown';
            const email = cells[2]?.textContent.trim() || 'N/A';
            const role = cells[3]?.textContent.trim() || 'User';
            const status = cells[4]?.querySelector('.badge')?.textContent.trim() || 'Unknown';

            
            document.getElementById('viewUserFullName').textContent = username;
            document.getElementById('viewUserUsername').textContent = username.toLowerCase().replace(' ', '');
            document.getElementById('viewUserEmail').textContent = email;
            document.getElementById('viewUserPhone').textContent = 'N/A';
            document.getElementById('viewUserJoined').textContent = new Date().toLocaleDateString();
            document.getElementById('viewUserRole').textContent = role;
            document.getElementById('viewUserStatus').textContent = status;
            document.getElementById('viewUserLastLogin').textContent = 'N/A';

            
            const statusBadge = document.getElementById('viewUserStatusBadge');
            statusBadge.textContent = status;
            statusBadge.className = status === 'Active' ? 'badge bg-label-success mt-2' : 'badge bg-label-secondary mt-2';

            
            document.getElementById('viewUserPermissions').innerHTML = `
                <span class="badge bg-label-primary">View</span>
                <span class="badge bg-label-info">Edit</span>
                <span class="badge bg-label-warning">Create</span>
            `;
        } else {
            console.error('Could not find user row for ID:', userId);
        }
    }

    
    function populateModal(user) {
        console.log('Populating modal with user data:', user);

        
        document.getElementById('viewUserFullName').textContent = user.full_name || user.username;
        document.getElementById('viewUserUsername').textContent = user.username;

        
        const avatarEl = document.getElementById('viewUser Avatar');
        if (user.avatar) {
            
            avatarEl.innerHTML = `<img src="${user.avatar}" alt="${user.username}" class="rounded-circle">`;
        } else {
            
            
            const initial = user.username.charAt(0).toUpperCase();
            avatarEl.innerHTML = `<span class="avatar-initial rounded-circle bg-label-primary">${initial}</span>`;
        }

        
        document.getElementById('viewUserEmail').textContent = user.email || 'N/A';
        document.getElementById('viewUserPhone').textContent = user.phone || 'N/A';
        document.getElementById('viewUserJoined').textContent = user.date_joined || 'N/A';

        
        document.getElementById('viewUserRole').textContent = user.role || 'User';
        document.getElementById('viewUserStatus').textContent = user.is_active ? 'Active' : 'Inactive';
        document.getElementById('viewUserLastLogin').textContent = user.last_login || 'Never';

        
        const statusBadge = document.getElementById('viewUserStatusBadge');
        statusBadge.textContent = user.is_active ? 'Active' : 'Inactive';
        statusBadge.className = user.is_active ? 'badge bg-label-success mt-2' : 'badge bg-label-secondary mt-2';

        
        if (user.permissions && user.permissions.length > 0) {
            
            const permissionsHTML = user.permissions.map(perm =>
                `<span class="badge bg-label-primary">${perm}</span>`
            ).join(' ');
            document.getElementById('viewUserPermissions').innerHTML = permissionsHTML;
        } else {
            
            document.getElementById('viewUserPermissions').innerHTML = '<span class="badge bg-label-secondary">No specific permissions</span>';
        }
    }

})();  
