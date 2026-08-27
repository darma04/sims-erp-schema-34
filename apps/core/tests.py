from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.core.permissions import get_accessible_submodules


class AccessibleSubmodulesTests(SimpleTestCase):
    @patch(
        "apps.core.permissions._get_role_permissions_cache",
        return_value={
            ("reimburse", None): {"can_view": True, "can_create": True, "can_edit": False, "can_delete": False},
            ("reimburse", "reimburse"): {"can_view": True, "can_create": True, "can_edit": False, "can_delete": False},
        },
    )
    @patch("apps.core.permissions.get_all_submodules_from_menu", return_value=["list", "pengajuan"])
    @patch("apps.core.permissions.get_user_role", return_value="USER")
    def test_legacy_unmapped_submodule_does_not_hide_sidebar_entries(self, _role, _menu, _permissions):
        user = SimpleNamespace(is_authenticated=True, is_superuser=False)
        self.assertEqual(get_accessible_submodules(user, "reimburse"), ["list", "pengajuan"])
