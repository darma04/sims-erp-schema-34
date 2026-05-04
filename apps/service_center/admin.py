"""
==========================================================================
 SERVICE CENTER ADMIN - Registrasi Model di Django Admin
==========================================================================
"""

from django.contrib import admin
from .models import (
    Pelanggan, Perangkat, KategoriService, JenisService,
    OrderService, ItemService, RiwayatStatus
)


class ItemServiceInline(admin.TabularInline):
    """Inline untuk detail layanan di admin OrderService."""
    model = ItemService
    extra = 1
    fields = ['jenis_service', 'nama_layanan', 'biaya', 'catatan']


class RiwayatStatusInline(admin.TabularInline):
    """Inline untuk riwayat status di admin OrderService."""
    model = RiwayatStatus
    extra = 0
    readonly_fields = ['status_sebelum', 'status_sesudah', 'catatan', 'diubah_oleh', 'timestamp']
    can_delete = False


@admin.register(Pelanggan)
class PelangganAdmin(admin.ModelAdmin):
    list_display = ['kode', 'nama', 'telepon', 'email', 'aktif', 'dibuat_pada']
    search_fields = ['kode', 'nama', 'telepon', 'email']
    list_filter = ['aktif']
    readonly_fields = ['kode', 'dibuat_pada', 'diupdate_pada']


@admin.register(Perangkat)
class PerangkatAdmin(admin.ModelAdmin):
    list_display = ['nama', 'icon', 'aktif', 'dibuat_pada']
    list_filter = ['aktif']


@admin.register(KategoriService)
class KategoriServiceAdmin(admin.ModelAdmin):
    list_display = ['nama', 'icon', 'aktif', 'dibuat_pada']
    search_fields = ['nama']
    list_filter = ['aktif']


@admin.register(JenisService)
class JenisServiceAdmin(admin.ModelAdmin):
    list_display = ['nama', 'kategori', 'harga_standar', 'estimasi_waktu', 'aktif']
    search_fields = ['nama']
    list_filter = ['kategori', 'aktif']
    list_select_related = ['kategori']


@admin.register(OrderService)
class OrderServiceAdmin(admin.ModelAdmin):
    list_display = ['nomor_service', 'kode_unik', 'pelanggan', 'merek', 'status', 'prioritas', 'biaya_akhir', 'tanggal_masuk']
    search_fields = ['nomor_service', 'kode_unik', 'pelanggan__nama', 'merek']
    list_filter = ['status', 'prioritas', 'status_bayar', 'jenis_perangkat']
    readonly_fields = ['nomor_service', 'kode_unik', 'dibuat_pada', 'diupdate_pada']
    inlines = [ItemServiceInline, RiwayatStatusInline]
    list_select_related = ['pelanggan', 'jenis_perangkat', 'teknisi']


@admin.register(ItemService)
class ItemServiceAdmin(admin.ModelAdmin):
    list_display = ['order_service', 'jenis_service', 'nama_layanan', 'biaya']
    search_fields = ['nama_layanan']
    list_select_related = ['order_service', 'jenis_service']


@admin.register(RiwayatStatus)
class RiwayatStatusAdmin(admin.ModelAdmin):
    list_display = ['order_service', 'status_sebelum', 'status_sesudah', 'diubah_oleh', 'timestamp']
    list_filter = ['status_sesudah']
    readonly_fields = ['timestamp']
    list_select_related = ['order_service', 'diubah_oleh']
