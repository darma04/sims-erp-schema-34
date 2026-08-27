from django import forms
from .models import ReimburseRequest, ReimburseItem
from apps.pos.models import MetodePembayaran
from apps.biaya.models import KategoriBiaya

ReimburseItemFormSet = forms.inlineformset_factory(
    ReimburseRequest, ReimburseItem,
    fields=['kategori', 'deskripsi', 'nominal', 'bukti'],
    extra=1, can_delete=True,
    widgets={
        'kategori': forms.Select(attrs={'class': 'form-select'}),
        'deskripsi': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Deskripsi pengeluaran'}),
        'nominal': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0', 'step': '0.01'}),
        'bukti': forms.FileInput(attrs={'class': 'form-control'}),
    }
)


class ReimburseForm(forms.ModelForm):
    class Meta:
        model = ReimburseRequest
        fields = ['tanggal', 'keterangan', 'metode_pembayaran']
        widgets = {
            'tanggal': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'keterangan': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Jelaskan tujuan reimburse...'}),
            'metode_pembayaran': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['metode_pembayaran'].queryset = MetodePembayaran.objects.filter(aktif=True)
        self.fields['metode_pembayaran'].required = False
        self.fields['metode_pembayaran'].empty_label = 'Pilih Metode Pembayaran (Opsional)'

    def clean(self):
        cleaned_data = super().clean()
        metode = cleaned_data.get('metode_pembayaran')
        if metode and not metode.aktif:
            raise forms.ValidationError('Metode pembayaran tidak aktif.')
        return cleaned_data


class ReimburseApproveForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class ReimburseRejectForm(forms.Form):
    alasan = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Alasan penolakan...'}),
        required=True, label="Alasan Penolakan"
    )


class ReimbursePayForm(forms.Form):
    metode_pembayaran = forms.ModelChoiceField(
        queryset=MetodePembayaran.objects.filter(aktif=True),
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=True, label="Metode Pembayaran", empty_label='Pilih Metode Pembayaran'
    )
    tanggal_bayar = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        required=True, label="Tanggal Bayar"
    )
