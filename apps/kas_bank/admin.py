from django.contrib import admin

from .models import KasBankAccount, KasBankReconciliation, KasBankTransaction, KasBankTransfer


@admin.register(KasBankAccount)
class KasBankAccountAdmin(admin.ModelAdmin):
    list_display = ("kode", "nama", "tipe", "akun", "saldo_awal", "aktif", "is_default")
    list_filter = ("tipe", "aktif", "is_default")
    search_fields = ("kode", "nama", "nomor_rekening", "nama_bank")


@admin.register(KasBankTransaction)
class KasBankTransactionAdmin(admin.ModelAdmin):
    list_display = ("nomor", "tanggal", "akun_kas_bank", "tipe", "jumlah", "status", "sumber_ref")
    list_filter = ("tipe", "status", "tanggal")
    search_fields = ("nomor", "deskripsi", "sumber_ref")
    date_hierarchy = "tanggal"


@admin.register(KasBankTransfer)
class KasBankTransferAdmin(admin.ModelAdmin):
    list_display = ("nomor", "tanggal", "dari_akun", "ke_akun", "jumlah", "biaya_admin", "status")
    list_filter = ("status", "tanggal")
    search_fields = ("nomor", "catatan")
    date_hierarchy = "tanggal"


@admin.register(KasBankReconciliation)
class KasBankReconciliationAdmin(admin.ModelAdmin):
    list_display = ("akun_kas_bank", "tanggal_mulai", "tanggal_akhir", "saldo_sistem", "saldo_statement", "selisih", "status")
    list_filter = ("status", "tanggal_mulai", "tanggal_akhir")
    search_fields = ("akun_kas_bank__kode", "akun_kas_bank__nama", "catatan")
