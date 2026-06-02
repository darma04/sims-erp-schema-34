"""
==========================================================================
 BOOTSTRAP LAYOUT VERTICAL - Inisialisasi Layout Vertikal
==========================================================================
 File Python untuk menginisialisasi context layout vertikal.
 Menyiapkan: sidebar menu, breadcrumb, template variables.
 Dipanggil oleh TemplateHelper untuk setiap request dengan layout vertikal.
 Dengan RBAC filtering — menyembunyikan menu yang tidak diizinkan.
"""

from django.conf import settings
import json

from web_project.template_helpers.theme import TemplateHelper

menu_file_path = settings.BASE_DIR / "templates" / "layout" / "partials" / "menu" / "vertical" / "json" / "vertical_menu.json"


class TemplateBootstrapLayoutVertical:
    def init(context):
        context.update(
            {
                "layout": "vertical",
                "content_navbar": True,
                "is_navbar": True,
                "is_menu": True,
                "is_footer": True,
                "navbar_detached": True,
            }
        )

        # map_context according to updated context values
        TemplateHelper.map_context(context)

        TemplateBootstrapLayoutVertical.init_menu_data(context)

        return context

    def init_menu_data(context):
        # Load the menu data from the JSON file
        menu_data = json.load(menu_file_path.open()) if menu_file_path.exists() else []

        # Get request from context (injected by TemplateLayout.init)
        request = context.get('request')

        # Filter menu based on user permissions
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            menu_data = TemplateBootstrapLayoutVertical.filter_menu_by_permission(
                menu_data, request.user
            )

        # Updated context with menu_data
        context.update({"menu_data": menu_data})

    def filter_menu_by_permission(menu_data, user):
        """
        Filter menu items based on user's role and permissions from the database.
        Uses RolePermission model to check if user has 'can_view' permission for each module.
        NOTE: 'allowed_roles' in menu JSON is IGNORED - only database permissions matter.
        """
        from apps.core.permissions import get_user_role, has_permission

        user_role = get_user_role(user)

        # Superuser sees everything
        if user_role == 'SUPERUSER':
            return menu_data

        # Mapping of menu slug to module permission name
        slug_to_module = {
            'dashboard': 'dashboard',
            'produk': 'produk',
            'inventory': 'inventory',
            'pembelian': 'pembelian',
            'penjualan': 'penjualan',
            'pos': 'pos',
            'invoice': 'pos',  # Invoice uses same module as POS
            'kas-bank': 'kas_bank',
            'kas_bank': 'kas_bank',
            'biaya': 'biaya',
            'hr': 'hr',
            'laporan': 'laporan',
            'users': 'user_management',
            'access-control': 'access_control',
            'activity-log': 'activity_log',
            'pengaturan': 'pengaturan',
            'automation': 'automation',
            'ai-assistant': 'ai_assistant',
            'ai-dashboard': 'ai_assistant',
            'fraud-detection': 'fraud_detection',
            'akuntansi': 'akuntansi',
            'laporan-keuangan': 'laporan_keuangan',
            'piutang': 'piutang',
            'hutang': 'hutang',
            'aset': 'aset',
            'pajak': 'pajak',
            # SIMS modules
            'service-center': 'service_center',
            'sparepart': 'sparepart',
        }

        filtered_menu = {"menu": []}

        for item in menu_data.get('menu', []):
            # Menu headers are always shown (we'll filter orphans after)
            if 'menu_header' in item:
                filtered_menu['menu'].append(item)
                continue

            slug = item.get('slug', '')

            # Check if user has permission for this module
            module_name = slug_to_module.get(slug, slug)

            # Check permission from database ONLY - ignore 'allowed_roles' from JSON
            if has_permission(user, 'read', module_name):
                filtered_menu['menu'].append(item)
            # If no permission, skip this menu item

        # Remove orphan menu headers (headers with no items following)
        cleaned_menu = {"menu": []}
        i = 0
        menu_items = filtered_menu['menu']

        while i < len(menu_items):
            item = menu_items[i]

            if 'menu_header' in item:
                # Check if there's at least one non-header item after this header
                has_content = False
                j = i + 1
                while j < len(menu_items):
                    if 'menu_header' in menu_items[j]:
                        break  # Found next header, no content for current header
                    else:
                        has_content = True
                        break

                if has_content:
                    cleaned_menu['menu'].append(item)
            else:
                cleaned_menu['menu'].append(item)

            i += 1

        return cleaned_menu
