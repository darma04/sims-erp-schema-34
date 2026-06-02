from django.contrib import admin
from apps.pajak.models import SettingPajak, FakturPajak


@admin.register(SettingPajak)
class SettingPajakAdmin(admin.ModelAdmin):
    list_display = ('tarif_ppn', 'npwp', 'nama_pkp', 'is_pkp')


@admin.register(FakturPajak)
class FakturPajakAdmin(admin.ModelAdmin):
    list_display = ('nomor_seri', 'tipe', 'tanggal', 'dpp', 'ppn', 'nama_lawan', 'status')
    list_filter = ('tipe', 'status', 'tanggal')
    search_fields = ('nomor_seri', 'nama_lawan')
