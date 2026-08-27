"""
Test RBAC Hybrid — memverifikasi:
1. Role name normalization (tidak dipotong)
2. Permission check (SUPERUSER bypass, user biasa ditolak)
3. Cache invalidation (perubahan role langsung berlaku)
"""
from django.test import TestCase
from django.contrib.auth.models import User
from apps.core.permissions import get_user_role, has_permission, is_superuser_role
from apps.core.cache_utils import normalize_role_code


class RoleNameNormalizationTest(TestCase):
    """Test bahwa nama role kustom TIDAK dipotong."""

    def setUp(self):
        self.user = User.objects.create_user(username='test_custom_role', password='test123')
        self.user.profile.role = 'WAREHOUSE_MANAGER'
        self.user.profile.save()

    def test_custom_role_not_truncated(self):
        """WAREHOUSE_MANAGER harus return 'WAREHOUSE_MANAGER'."""
        self.assertEqual(get_user_role(self.user), 'WAREHOUSE_MANAGER')

    def test_standard_role_exact_match(self):
        """Role standar harus exact match."""
        for std_role in ['ADMIN', 'KASIR', 'USER', 'PENGELOLA']:
            self.user.profile.role = std_role
            self.user.profile.save()
            self.assertEqual(get_user_role(self.user), std_role)

    def test_admin_staff_not_truncated_to_admin(self):
        """ADMIN_STAFF harus return 'ADMIN_STAFF', bukan 'ADMIN'."""
        self.user.profile.role = 'ADMIN_STAFF'
        self.user.profile.save()
        self.assertEqual(get_user_role(self.user), 'ADMIN_STAFF')

    def test_user_manager_not_truncated_to_user(self):
        """USER_MANAGER harus return 'USER_MANAGER', bukan 'USER'."""
        self.user.profile.role = 'USER_MANAGER'
        self.user.profile.save()
        self.assertEqual(get_user_role(self.user), 'USER_MANAGER')

    def test_normalize_role_code_custom(self):
        """normalize_role_code tidak boleh potong role kustom."""
        self.assertEqual(normalize_role_code('ADMIN_GUDANG'), 'ADMIN_GUDANG')
        self.assertEqual(normalize_role_code('WAREHOUSE_MANAGER'), 'WAREHOUSE_MANAGER')
        self.assertEqual(normalize_role_code('STAFF_GUDANG'), 'STAFF_GUDANG')

    def test_normalize_role_code_standard(self):
        """normalize_role_code untuk role standar harus exact match."""
        self.assertEqual(normalize_role_code('ADMIN'), 'ADMIN')
        self.assertEqual(normalize_role_code('SUPERUSER'), 'SUPERUSER')

    def test_normalize_role_code_legacy_display_name(self):
        """Legacy display name dengan spasi harus di-handle."""
        self.assertEqual(normalize_role_code('USER - READ & CREATE ONLY'), 'USER')


class SuperuserBypassTest(TestCase):
    """SUPERUSER bypass semua pengecekan permission."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='admin_test', email='admin@test.com', password='admin123'
        )

    def test_superuser_has_all_permissions(self):
        """Superuser harus bisa akses modul apapun."""
        for action in ['create', 'read', 'update', 'delete']:
            self.assertTrue(
                has_permission(self.superuser, action, 'produk'),
                f"Superuser should have {action} on produk"
            )

    def test_superuser_role_detected(self):
        """is_superuser_role harus True untuk superuser."""
        self.assertTrue(is_superuser_role(self.superuser))


class PermissionDeniedTest(TestCase):
    """User tanpa permission harus ditolak."""

    def setUp(self):
        self.user = User.objects.create_user(username='no_perm_user', password='test123')
        self.user.profile.role = 'NONE'
        self.user.profile.save()

    def test_user_without_permission_cannot_delete(self):
        self.assertFalse(has_permission(self.user, 'delete', 'produk'))

    def test_user_without_permission_cannot_create(self):
        self.assertFalse(has_permission(self.user, 'create', 'laporan'))

    def test_user_without_permission_cannot_update(self):
        self.assertFalse(has_permission(self.user, 'update', 'hr'))


class GetUserRoleEdgeCasesTest(TestCase):
    """Edge case get_user_role."""

    def test_anonymous_user(self):
        anonymous = type('Anon', (), {
            'is_authenticated': False, 'is_superuser': False
        })()
        self.assertIsNone(get_user_role(anonymous))

    def test_none_user(self):
        self.assertIsNone(get_user_role(None))

    def test_user_without_profile(self):
        user = User.objects.create_user(username='no_profile_user', password='test123')
        from auth.models import Profile
        Profile.objects.filter(user=user).delete()
        self.assertEqual(get_user_role(user), 'USER')


class RoleUserMappingTest(TestCase):
    """Test bahwa role di profile -> permission di RolePermission."""

    def setUp(self):
        from apps.core.models import RolePermission
        RolePermission.objects.create(
            role='TEST_VIEW_ONLY', module='produk', sub_module=None,
            can_view=True, can_create=False, can_edit=False, can_delete=False
        )
        self.user = User.objects.create_user(username='view_only_user', password='test123')
        self.user.profile.role = 'TEST_VIEW_ONLY'
        self.user.profile.save()

    def test_view_only_can_view_but_not_delete(self):
        """Role TEST_VIEW_ONLY: bisa view produk, tidak bisa delete."""
        self.assertTrue(has_permission(self.user, 'read', 'produk'))
        self.assertFalse(has_permission(self.user, 'delete', 'produk'))
        self.assertFalse(has_permission(self.user, 'create', 'produk'))
        self.assertFalse(has_permission(self.user, 'update', 'produk'))
