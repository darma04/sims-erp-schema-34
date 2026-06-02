from django.contrib import admin
from apps.hutang.models import Hutang, PembayaranHutang


class PembayaranHutangInline(admin.TabularInline):
    model = PembayaranHutang
    extra = 0
    readonly_fields = ('dibuat_pada',)


@admin.register(Hutang)
class HutangAdmin(admin.ModelAdmin):
    list_display = ('nomor', 'supplier', 'jumlah_total', 'jumlah_dibayar', 'status', 'jatuh_tempo')
    list_filter = ('status', 'sumber', 'cabang')
    search_fields = ('nomor', 'supplier__nama')
    inlines = [PembayaranHutangInline]


@admin.register(PembayaranHutang)
class PembayaranHutangAdmin(admin.ModelAdmin):
    list_display = ('hutang', 'tanggal', 'jumlah', 'metode_pembayaran')
    list_filter = ('tanggal',)
