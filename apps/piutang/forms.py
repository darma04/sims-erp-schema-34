"""
==========================================================================
 PIUTANG FORMS
==========================================================================
"""
from django import forms
from apps.piutang.models import Piutang, PembayaranPiutang
from apps.penjualan.models import Customer
from apps.pos.models import MetodePembayaran
from apps.produk.models import Gudang
from datetime import date


class PiutangForm(forms.ModelForm):
    """Form untuk input piutang manual."""
    class Meta:
        model = Piutang
        fields = ['customer', 'jumlah_total', 'tanggal', 'jatuh_tempo', 'cabang', 'keterangan']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'jumlah_total': forms.NumberInput(attrs={'class': 'form-control text-end', 'min': '0', 'step': '0.01', 'placeholder': '0'}),
            'tanggal': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'jatuh_tempo': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'cabang': forms.Select(attrs={'class': 'form-select'}),
            'keterangan': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Customer.objects.filter(aktif=True)
        self.fields['cabang'].queryset = Gudang.objects.filter(aktif=True)
        self.fields['cabang'].empty_label = 'Semua Cabang (Pusat)'
        self.fields['cabang'].required = False
        self.fields['jatuh_tempo'].required = False
        self.fields['keterangan'].required = False
        if not self.instance.pk:
            self.fields['tanggal'].initial = date.today()


class PembayaranPiutangForm(forms.ModelForm):
    """Form untuk pembayaran/pelunasan piutang."""
    class Meta:
        model = PembayaranPiutang
        fields = ['tanggal', 'jumlah', 'metode_pembayaran', 'keterangan']
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'jumlah': forms.NumberInput(attrs={'class': 'form-control text-end', 'min': '1', 'step': '0.01', 'placeholder': '0'}),
            'metode_pembayaran': forms.Select(attrs={'class': 'form-select'}),
            'keterangan': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Keterangan pembayaran'}),
        }

    def __init__(self, *args, piutang=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.piutang = piutang
        self.fields['metode_pembayaran'].queryset = MetodePembayaran.objects.filter(aktif=True)
        self.fields['metode_pembayaran'].empty_label = 'Pilih Metode'
        self.fields['keterangan'].required = False
        if not self.instance.pk:
            self.fields['tanggal'].initial = date.today()
            if piutang:
                self.fields['jumlah'].initial = piutang.sisa
                self.fields['jumlah'].widget.attrs['max'] = str(piutang.sisa)

    def clean_jumlah(self):
        jumlah = self.cleaned_data['jumlah']
        if self.piutang and jumlah > self.piutang.sisa:
            raise forms.ValidationError(f'Jumlah bayar (Rp {jumlah:,.0f}) melebihi sisa piutang (Rp {self.piutang.sisa:,.0f})')
        if jumlah <= 0:
            raise forms.ValidationError('Jumlah bayar harus lebih dari 0')
        return jumlah
