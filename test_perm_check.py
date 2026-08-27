import os, sys
sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from apps.core.permissions import has_permission, get_user_role, _get_role_permissions_cache
from django.contrib.auth.models import User

for role in ['SUPERUSER', 'ADMIN', 'USER', 'KASIR']:
    try:
        cache = _get_role_permissions_cache(role)
        rmb_keys = [(m,s) for (m,s) in cache.keys() if m == 'reimburse']
        print(f'\n=== reimburse ({role}): {len(rmb_keys)} entries ===')
        for (m,s) in rmb_keys:
            p = cache[(m,s)]
            nm = s or "None"
            print(f'  ({m}, {nm}): v={p.get("can_view")}, c={p.get("can_create")}, e={p.get("can_edit")}, d={p.get("can_delete")}')
        
        appr_keys = [(m,s) for (m,s) in cache.keys() if m == 'approval_center']
        for (m,s) in appr_keys:
            p = cache[(m,s)]
            nm = s or "None"
            print(f'  ({m}, {nm}): v={p.get("can_view")}, c={p.get("can_create")}')
    except Exception as e:
        print(f'  ERROR: {e}')

print('\n=== LIVE TEST ===')
for u in User.objects.all()[:4]:
    role = get_user_role(u)
    r1 = has_permission(u, "view", "reimburse", "daftar_reimburse")
    r2 = has_permission(u, "create", "reimburse", "pengajuan")
    r3 = has_permission(u, "view", "approval_center", None)
    print(f'{u.username} ({role}): rmb_list={r1}, rmb_create={r2}, approval={r3}')
print('DONE')
