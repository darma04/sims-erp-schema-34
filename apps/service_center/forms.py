"""
==========================================================================
 SERVICE CENTER FORMS - Form untuk Manajemen Service Elektronik
==========================================================================
 Form Django untuk modul Service Center:
 - PelangganForm: CRUD pelanggan
 - PerangkatForm: CRUD jenis perangkat
 - KategoriServiceForm: CRUD kategori service
 - JenisServiceForm: CRUD jenis layanan service
 - OrderServiceForm: Form penerimaan unit service
 - ItemServiceFormSet: Formset inline untuk detail layanan
 - UpdateStatusForm: Update status order
 - PembayaranForm: Update pembayaran
==========================================================================
"""

from django import forms
from django.forms import inlineformset_factory

from .models import (
    Pelanggan, Perangkat, KategoriService, JenisService,
    OrderService, ItemService
)


class PelangganForm(forms.ModelForm):
    """Form untuk CRUD data pelanggan."""
    class Meta:
        model = Pelanggan
        fields = ['nama', 'telepon', 'email', 'alamat', 'aktif']
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nama lengkap pelanggan'}),
            'telepon': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '08xxxxxxxxxx'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@contoh.com'}),
            'alamat': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Alamat lengkap'}),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class PerangkatForm(forms.ModelForm):
    """Form untuk CRUD jenis perangkat."""
    class Meta:
        model = Perangkat
        fields = ['nama', 'deskripsi', 'icon', 'aktif']
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contoh: HP Android'}),
            'deskripsi': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'icon': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ri-smartphone-line'}),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class KategoriServiceForm(forms.ModelForm):
    """Form untuk CRUD kategori service (Hardware, Software, dll)."""
    class Meta:
        model = KategoriService
        fields = ['nama', 'deskripsi', 'icon', 'aktif']
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contoh: Hardware'}),
            'deskripsi': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'icon': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ri-tools-line'}),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class JenisServiceForm(forms.ModelForm):
    """Form untuk CRUD jenis layanan service."""
    class Meta:
        model = JenisService
        fields = ['kategori', 'nama', 'deskripsi', 'foto', 'harga_standar', 'estimasi_waktu', 'aktif']
        widgets = {
            'kategori': forms.Select(attrs={'class': 'form-select'}),
            'nama': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contoh: Ganti LCD'}),
            'deskripsi': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'foto': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'harga_standar': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0'}),
            'estimasi_waktu': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '1-2 jam'}),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class OrderServiceForm(forms.ModelForm):
    """Form penerimaan unit service baru (intake)."""
    class Meta:
        model = OrderService
        fields = [
            'pelanggan', 'jenis_perangkat', 'merek', 'model_tipe',
            'nomor_seri', 'warna', 'keluhan', 'kondisi_fisik',
            'kelengkapan', 'password_perangkat', 'gambar_perangkat',
            'prioritas', 'estimasi_biaya', 'estimasi_selesai',
            'teknisi', 'cabang', 'catatan_internal', 'metode_pembayaran',
        ]
        widgets = {
            'pelanggan': forms.Select(attrs={'class': 'form-select'}),
            'jenis_perangkat': forms.Select(attrs={'class': 'form-select'}),
            'merek': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contoh: Samsung, Apple, LG'}),
            'model_tipe': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contoh: Galaxy A54, iPhone 15'}),
            'nomor_seri': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'IMEI / Serial Number'}),
            'warna': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contoh: Hitam'}),
            'keluhan': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Deskripsikan keluhan pelanggan...'}),
            'kondisi_fisik': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Lecet, retak, penyok, dll'}),
            'kelengkapan': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Charger, dus, SIM card, dll'}),
            'password_perangkat': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'PIN / Pattern / Password'}),
            'gambar_perangkat': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'prioritas': forms.Select(attrs={'class': 'form-select'}),
            'estimasi_biaya': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0'}),
            'estimasi_selesai': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'teknisi': forms.Select(attrs={'class': 'form-select'}),
            'cabang': forms.Select(attrs={'class': 'form-select'}),
            'catatan_internal': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'metode_pembayaran': forms.Select(attrs={'class': 'form-select'}),
        }


class ItemServiceForm(forms.ModelForm):
    """Form untuk item layanan per order service."""
    class Meta:
        model = ItemService
        fields = ['jenis_service', 'nama_layanan', 'biaya', 'catatan']
        widgets = {
            'jenis_service': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'nama_layanan': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Nama layanan'}),
            'biaya': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': '0'}),
            'catatan': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Catatan'}),
        }


# Inline formset untuk detail layanan di dalam order service
ItemServiceFormSet = inlineformset_factory(
    OrderService,
    ItemService,
    form=ItemServiceForm,
    extra=2,
    max_num=20,
    can_delete=True,
)


class UpdateStatusForm(forms.Form):
    """Form untuk update status order service."""
    status = forms.ChoiceField(
        choices=OrderService.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    catatan = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Catatan perubahan status...'
        })
    )
    catatan_teknisi = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Catatan dari teknisi...'
        })
    )
    biaya_akhir = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '0'
        })
    )


class PembayaranForm(forms.Form):
    """Form untuk update pembayaran."""
    status_bayar = forms.ChoiceField(
        choices=OrderService.STATUS_BAYAR_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    dp_bayar = forms.DecimalField(
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': '0'
        })
    )
    metode_pembayaran = forms.ModelChoiceField(
        required=False,
        queryset=None,
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label='-- Pilih Metode --'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from apps.pos.models import MetodePembayaran
            self.fields['metode_pembayaran'].queryset = MetodePembayaran.objects.filter(aktif=True)
        except Exception:
            self.fields['metode_pembayaran'].queryset = MetodePembayaran.objects.none()
