"""
==========================================================================
 ASET FORMS
==========================================================================
"""
from django import forms
from apps.aset.models import AsetTetap, DisposalAset
from apps.akuntansi.models import Akun
from apps.pembelian.models import Supplier
from apps.produk.models import Gudang
from datetime import date


class AsetTetapForm(forms.ModelForm):
    class Meta:
        model = AsetTetap
        fields = ['nama', 'kategori', 'deskripsi', 'akun_aset', 'harga_perolehan',
                  'nilai_residu', 'umur_ekonomis', 'tanggal_perolehan',
                  'metode_penyusutan', 'supplier', 'cabang']
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nama aset'}),
            'kategori': forms.Select(attrs={'class': 'form-select'}),
            'deskripsi': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'akun_aset': forms.Select(attrs={'class': 'form-select'}),
            'harga_perolehan': forms.NumberInput(attrs={'class': 'form-control text-end', 'min': '0', 'step': '0.01'}),
            'nilai_residu': forms.NumberInput(attrs={'class': 'form-control text-end', 'min': '0', 'step': '0.01'}),
            'umur_ekonomis': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'placeholder': 'dalam bulan'}),
            'tanggal_perolehan': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'metode_penyusutan': forms.Select(attrs={'class': 'form-select'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'cabang': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['akun_aset'].queryset = Akun.objects.filter(tipe='aset', is_active=True)
        self.fields['akun_aset'].empty_label = 'Pilih Akun Aset'
        self.fields['akun_aset'].required = False
        self.fields['supplier'].queryset = Supplier.objects.filter(aktif=True)
        self.fields['supplier'].empty_label = 'Pilih Supplier (opsional)'
        self.fields['supplier'].required = False
        self.fields['cabang'].queryset = Gudang.objects.filter(aktif=True)
        self.fields['cabang'].empty_label = 'Pusat'
        self.fields['cabang'].required = False
        self.fields['deskripsi'].required = False
        if not self.instance.pk:
            self.fields['tanggal_perolehan'].initial = date.today()


class DisposalAsetForm(forms.ModelForm):
    class Meta:
        model = DisposalAset
        fields = ['tipe', 'tanggal', 'harga_jual', 'keterangan']
        widgets = {
            'tipe': forms.Select(attrs={'class': 'form-select'}),
            'tanggal': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'harga_jual': forms.NumberInput(attrs={'class': 'form-control text-end', 'min': '0', 'step': '0.01'}),
            'keterangan': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['keterangan'].required = False
        if not self.instance.pk:
            self.fields['tanggal'].initial = date.today()
