from django.contrib import admin
from .models import ReimburseRequest, ReimburseItem


class ReimburseItemInline(admin.TabularInline):
    model = ReimburseItem
    extra = 0


@admin.register(ReimburseRequest)
class ReimburseRequestAdmin(admin.ModelAdmin):
    list_display = ['nomor', 'pemohon', 'tanggal', 'total', 'status', 'dibuat_pada']
    list_filter = ['status', 'tanggal']
    search_fields = ['nomor', 'pemohon__username', 'keterangan']
    inlines = [ReimburseItemInline]
    readonly_fields = ['nomor', 'dibuat_pada', 'diupdate_pada']


@admin.register(ReimburseItem)
class ReimburseItemAdmin(admin.ModelAdmin):
    list_display = ['request', 'kategori', 'deskripsi', 'nominal']
