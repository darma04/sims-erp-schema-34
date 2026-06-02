from django.contrib import admin
from apps.piutang.models import Piutang, PembayaranPiutang


class PembayaranPiutangInline(admin.TabularInline):
    model = PembayaranPiutang
    extra = 0
    readonly_fields = ('dibuat_pada',)


@admin.register(Piutang)
class PiutangAdmin(admin.ModelAdmin):
    list_display = ('nomor', 'customer', 'jumlah_total', 'jumlah_dibayar', 'status', 'jatuh_tempo')
    list_filter = ('status', 'sumber', 'cabang')
    search_fields = ('nomor', 'customer__nama')
    inlines = [PembayaranPiutangInline]


@admin.register(PembayaranPiutang)
class PembayaranPiutangAdmin(admin.ModelAdmin):
    list_display = ('piutang', 'tanggal', 'jumlah', 'metode_pembayaran')
    list_filter = ('tanggal',)
