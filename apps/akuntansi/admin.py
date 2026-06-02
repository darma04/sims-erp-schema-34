"""
==========================================================================
 AKUNTANSI ADMIN - Registrasi model ke Django Admin
==========================================================================
"""
from django.contrib import admin
from apps.akuntansi.models import Akun, PeriodeAkuntansi, JurnalEntry, JurnalLine


class JurnalLineInline(admin.TabularInline):
    """Inline untuk JurnalLine di dalam JurnalEntry admin."""
    model = JurnalLine
    extra = 2


@admin.register(Akun)
class AkunAdmin(admin.ModelAdmin):
    list_display = ['kode', 'nama', 'tipe', 'sub_tipe', 'saldo_normal', 'is_active']
    list_filter = ['tipe', 'saldo_normal', 'is_active']
    search_fields = ['kode', 'nama']
    ordering = ['kode']


@admin.register(PeriodeAkuntansi)
class PeriodeAkuntansiAdmin(admin.ModelAdmin):
    list_display = ['nama', 'tanggal_mulai', 'tanggal_akhir', 'is_aktif', 'is_tutup']
    list_filter = ['is_aktif', 'is_tutup']


@admin.register(JurnalEntry)
class JurnalEntryAdmin(admin.ModelAdmin):
    list_display = ['nomor', 'tanggal', 'deskripsi', 'sumber', 'is_posted']
    list_filter = ['sumber', 'is_posted']
    search_fields = ['nomor', 'deskripsi']
    inlines = [JurnalLineInline]
