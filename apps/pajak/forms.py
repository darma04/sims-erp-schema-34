from django import forms
from apps.pajak.models import SettingPajak, FakturPajak
from datetime import date


class SettingPajakForm(forms.ModelForm):
    class Meta:
        model = SettingPajak
        fields = ['tarif_ppn', 'npwp', 'nama_pkp', 'alamat_pkp', 'is_pkp']
        widgets = {
            'tarif_ppn': forms.NumberInput(attrs={'class': 'form-control text-end', 'step': '0.01'}),
            'npwp': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'XX.XXX.XXX.X-XXX.XXX'}),
            'nama_pkp': forms.TextInput(attrs={'class': 'form-control'}),
            'alamat_pkp': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_pkp': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class FakturPajakForm(forms.ModelForm):
    class Meta:
        model = FakturPajak
        fields = ['nomor_seri', 'tipe', 'tanggal', 'dpp', 'tarif_ppn',
                  'nama_lawan', 'npwp_lawan', 'sales_order', 'purchase_order',
                  'pos_transaction', 'keterangan']
        widgets = {
            'nomor_seri': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '000-00.00000000'}),
            'tipe': forms.Select(attrs={'class': 'form-select'}),
            'tanggal': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'dpp': forms.NumberInput(attrs={'class': 'form-control text-end', 'min': '0', 'step': '0.01'}),
            'tarif_ppn': forms.NumberInput(attrs={'class': 'form-control text-end', 'step': '0.01'}),
            'nama_lawan': forms.TextInput(attrs={'class': 'form-control'}),
            'npwp_lawan': forms.TextInput(attrs={'class': 'form-control'}),
            'sales_order': forms.Select(attrs={'class': 'form-select'}),
            'purchase_order': forms.Select(attrs={'class': 'form-select'}),
            'pos_transaction': forms.Select(attrs={'class': 'form-select'}),
            'keterangan': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['keterangan'].required = False
        self.fields['npwp_lawan'].required = False
        self.fields['sales_order'].required = False
        self.fields['purchase_order'].required = False
        self.fields['pos_transaction'].required = False
        if not self.instance.pk:
            self.fields['tanggal'].initial = date.today()
            setting = SettingPajak.get_setting()
            self.fields['tarif_ppn'].initial = setting.tarif_ppn
