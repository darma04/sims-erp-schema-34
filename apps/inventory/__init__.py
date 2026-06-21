"""
==========================================================================
 INVENTORY APP - Modul Transfer Stok & Adjustment Stok
==========================================================================
 Package ini menangani pergerakan stok antar gudang dan koreksi manual.

 Berisi:
 - models.py → TransferStok, TransferStokItem, AdjustmentStok
 - views.py  → CRUD transfer stok & adjustment stok
 - forms.py  → Form Django + formset untuk input transfer/adjustment
 - urls.py   → Routing URL modul inventory

 Alur Transfer: Draft → Submitted → Approved → Completed (stok berubah)
 Alur Adjustment: Langsung update stok saat save (tanpa approval)

 Terhubung dengan:
 - apps/produk/ → Produk, Gudang, Stok (data master)
 - apps/activity_log/ → Log perubahan stok
 - apps/dashboard/ → Statistik inventory di dashboard
 - apps/laporan/ → Laporan stok
==========================================================================
"""
from django.apps import AppConfig


class InventoryConfig(AppConfig):
    """
    Konfigurasi aplikasi Inventory.

    Atribut:
    - default_auto_field: Tipe ID default untuk model (BigAutoField = int 64-bit)
    - name: Path lengkap app (harus cocok dengan INSTALLED_APPS di settings.py)
    - verbose_name: Nama yang ditampilkan di Django Admin
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.inventory'
    verbose_name = 'Inventory'

    def ready(self):
        import apps.inventory.signals  # noqa: F401
