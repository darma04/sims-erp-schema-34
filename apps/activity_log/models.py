"""
==========================================================================
 ACTIVITY LOG MODELS - Model Pencatatan Aktivitas User
==========================================================================
 File ini berisi model UserActivity — sistem audit trail (jejak aktivitas)
 yang mencatat SEMUA aksi user di dalam aplikasi ERP.

 Mengapa Audit Trail Penting?
 - Keamanan: Mengetahui siapa yang mengubah data dan kapan
 - Debugging: Melacak masalah berdasarkan kronologi aksi
 - Compliance: Memenuhi standar akuntabilitas data bisnis

 Model: UserActivity
 ├── Informasi Aksi: user, action, timestamp
 ├── Detail Objek: model_name, object_id, object_repr
 ├── Perubahan Data: changes (JSON format → field lama vs baru)
 ├── Tracking Stok: source_type, quantity_before/after/change, gudang
 └── Info Request: ip_address, user_agent

 Terhubung dengan:
 - middleware.py → Menyimpan request di thread-local agar bisa diakses di signals
 - signals.py → Auto-log setiap create/update/delete model
 - stock_signals.py → Log detail khusus perubahan stok
 - views.py → Menampilkan halaman log aktivitas

 Teknologi Django yang digunakan:
 - models.Model → Base class untuk semua model Django (ORM)
 - ForeignKey → Relasi many-to-one ke tabel User
 - on_delete=SET_NULL → Jika user dihapus, log tetap ada (NULL)
 - auto_now_add=True → Timestamp otomatis saat record dibuat
 - Meta.indexes → Mempercepat query dengan database index
==========================================================================
"""
from django.db import models
# Import dari framework Django
from django.contrib.auth.models import User
import json


class UserActivity(models.Model):
    """
    Model utama untuk menyimpan log aktivitas user.
    Setiap aksi (login, CRUD, stok, export) dicatat sebagai 1 record.
    Data disimpan secara permanen untuk audit trail.
    """
    # ╔══════════════════════════════════════════════════════════════╗
    # ║ CHOICES - Pilihan nilai untuk field action dan source_type  ║
    # ╚══════════════════════════════════════════════════════════════╝
    ACTION_CHOICES = [
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('create', 'Tambah Data'),
        ('update', 'Edit Data'),
        ('delete', 'Hapus Data'),
        ('view', 'Lihat Data'),
        ('export', 'Export Data'),
        ('import', 'Import Data'),
        ('approve', 'Approve'),
        ('reject', 'Reject'),
        ('cancel', 'Batalkan'),
        # Stock-specific actions
        ('stock_in', 'Stok Masuk'),
        ('stock_out', 'Stok Keluar'),
        ('stock_adjustment', 'Penyesuaian Stok'),
        ('stock_transfer_in', 'Transfer Masuk'),
        ('stock_transfer_out', 'Transfer Keluar'),
    ]
    
    SOURCE_TYPE_CHOICES = [
        ('purchase', 'Pembelian (PO)'),
        ('sales', 'Penjualan (SO)'),
        ('pos', 'Point of Sale'),
        ('transfer', 'Transfer Stok'),
        ('adjustment', 'Adjustment'),
        ('manual', 'Input Manual'),
    ]
    
    # user — Relasi FK
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='activities', verbose_name="User")
    # action — Teks pendek
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, verbose_name="Aksi")
    # model_name — Teks pendek
    model_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Model")
    # object_id — Teks pendek
    object_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="Object ID")
    # object_repr — Teks pendek
    object_repr = models.CharField(max_length=200, blank=True, null=True, verbose_name="Object")
    # description — Teks panjang
    description = models.TextField(blank=True, null=True, verbose_name="Deskripsi")
    
    # Detail perubahan (JSON)
    changes = models.TextField(blank=True, null=True, verbose_name="Perubahan")
    
    # Source tracking - untuk mengetahui sumber perubahan stok
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES, blank=True, null=True, verbose_name="Sumber")
    # source_id — Teks pendek
    source_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID Sumber")
    # source_repr — Teks pendek
    source_repr = models.CharField(max_length=200, blank=True, null=True, verbose_name="Referensi Sumber")
    
    # Quantity tracking - untuk detail perubahan jumlah stok
    quantity_before = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, verbose_name="Qty Sebelum")
    # quantity_after — Angka desimal
    quantity_after = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, verbose_name="Qty Sesudah")
    # quantity_change — Angka desimal
    quantity_change = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, verbose_name="Perubahan Qty")
    
    # Gudang tracking - untuk stok per gudang
    gudang_id = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID Gudang")
    # gudang_name — Teks pendek
    gudang_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nama Gudang")
    
    # Request info
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name="IP Address")
    # user_agent — Teks panjang
    user_agent = models.TextField(blank=True, null=True, verbose_name="User Agent")
    
    # timestamp — Tanggal & waktu
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Waktu")
    
    class Meta:
        """Konfigurasi metadata model untuk Django."""
        verbose_name = "Log Aktivitas"
        verbose_name_plural = "Log Aktivitas"
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
            models.Index(fields=['model_name', 'object_id']),
            models.Index(fields=['source_type', '-timestamp']),
        ]
    
    def __str__(self):
        """Representasi string objek untuk admin dan debugging."""
        return f"{self.user.username if self.user else 'Unknown'} - {self.get_action_display()} - {self.timestamp.strftime('%d/%m/%Y %H:%M')}"
    
    def set_changes(self, changes_dict):
        """Menyimpan perubahan dari dictionary ke field changes (format JSON)"""
        self.changes = json.dumps(changes_dict, ensure_ascii=False)
    
    def get_changes(self):
        """Mengambil perubahan sebagai dictionary dari field changes (JSON→dict)"""
        if self.changes:
            try:
                return json.loads(self.changes)
            except Exception:
                return {}
        return {}
    
    def get_quantity_display(self):
        """Mendapatkan tampilan perubahan quantity yang sudah diformat"""
        if self.quantity_change is not None:
            sign = '+' if self.quantity_change > 0 else ''
            return f"{sign}{self.quantity_change:,.0f}"
        return None
    
    @property
    def is_stock_action(self):
        """Mengecek apakah aksi ini terkait stok (stock_in, stock_out, dll)"""
        return self.action in ['stock_in', 'stock_out', 'stock_adjustment', 'stock_transfer_in', 'stock_transfer_out']
