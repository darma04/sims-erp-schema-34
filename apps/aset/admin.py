from django.contrib import admin
from apps.aset.models import AsetTetap, Penyusutan, DisposalAset


class PenyusutanInline(admin.TabularInline):
    model = Penyusutan
    extra = 0
    readonly_fields = ('dibuat_pada',)


class DisposalInline(admin.TabularInline):
    model = DisposalAset
    extra = 0


@admin.register(AsetTetap)
class AsetTetapAdmin(admin.ModelAdmin):
    list_display = ('kode', 'nama', 'kategori', 'harga_perolehan', 'status', 'cabang')
    list_filter = ('kategori', 'status', 'cabang', 'metode_penyusutan')
    search_fields = ('kode', 'nama')
    inlines = [PenyusutanInline, DisposalInline]


@admin.register(Penyusutan)
class PenyusutanAdmin(admin.ModelAdmin):
    list_display = ('aset', 'bulan', 'tahun', 'jumlah', 'akumulasi')
    list_filter = ('tahun', 'bulan')


@admin.register(DisposalAset)
class DisposalAsetAdmin(admin.ModelAdmin):
    list_display = ('aset', 'tipe', 'tanggal', 'harga_jual', 'laba_rugi')
    list_filter = ('tipe', 'tanggal')
