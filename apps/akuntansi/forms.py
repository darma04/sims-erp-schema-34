"""
==========================================================================
 AKUNTANSI FORMS - Form untuk Chart of Accounts, Jurnal & Periode
==========================================================================
"""

from django import forms
from django.forms import inlineformset_factory
from apps.akuntansi.models import Akun, PeriodeAkuntansi, JurnalEntry, JurnalLine
from apps.produk.models import Gudang
from datetime import date


class AkunForm(forms.ModelForm):
    """Form CRUD Chart of Accounts."""
    class Meta:
        model = Akun
        fields = ['kode', 'nama', 'tipe', 'sub_tipe', 'parent', 'saldo_normal', 'deskripsi', 'is_active']
        widgets = {
            'kode': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contoh: 1-1000'}),
            'nama': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nama akun'}),
            'tipe': forms.Select(attrs={'class': 'form-select', 'id': 'id_tipe'}),
            'sub_tipe': forms.Select(attrs={'class': 'form-select'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'saldo_normal': forms.Select(attrs={'class': 'form-select'}),
            'deskripsi': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent'].queryset = Akun.objects.filter(is_active=True)
        self.fields['parent'].empty_label = '— Tanpa Induk (Akun Utama) —'
        self.fields['parent'].required = False
        self.fields['sub_tipe'].required = False
        self.fields['deskripsi'].required = False


class PeriodeAkuntansiForm(forms.ModelForm):
    """Form CRUD Periode Akuntansi."""
    class Meta:
        model = PeriodeAkuntansi
        fields = ['nama', 'tanggal_mulai', 'tanggal_akhir', 'is_aktif']
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contoh: Januari 2026'}),
            'tanggal_mulai': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'tanggal_akhir': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class JurnalEntryForm(forms.ModelForm):
    """Form header Jurnal Entry (untuk jurnal manual)."""
    class Meta:
        model = JurnalEntry
        fields = ['tanggal', 'deskripsi', 'cabang', 'periode']
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'deskripsi': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Keterangan jurnal...'}),
            'cabang': forms.Select(attrs={'class': 'form-select'}),
            'periode': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cabang'].queryset = Gudang.objects.filter(aktif=True)
        self.fields['cabang'].empty_label = 'Semua Cabang (Pusat)'
        self.fields['cabang'].required = False

        # Hanya tampilkan periode yang aktif dan belum ditutup
        self.fields['periode'].queryset = PeriodeAkuntansi.objects.filter(is_aktif=True, is_tutup=False)
        self.fields['periode'].empty_label = 'Pilih Periode (Opsional)'
        self.fields['periode'].required = False

        if not self.instance.pk:
            self.fields['tanggal'].initial = date.today()

    def clean(self):
        """Validasi: periode harus aktif dan belum ditutup jika dipilih."""
        cleaned_data = super().clean()
        periode = cleaned_data.get('periode')
        tanggal = cleaned_data.get('tanggal')

        if periode:
            if periode.is_tutup:
                self.add_error('periode', 'Periode ini sudah ditutup. Tidak dapat menerima jurnal baru.')
            if not periode.is_aktif:
                self.add_error('periode', 'Periode ini tidak aktif. Pilih periode yang sedang aktif.')
            if tanggal and not (periode.tanggal_mulai <= tanggal <= periode.tanggal_akhir):
                self.add_error('periode', 'Tanggal jurnal berada di luar rentang periode yang dipilih.')
        elif tanggal:
            closed_period = PeriodeAkuntansi.objects.filter(
                tanggal_mulai__lte=tanggal,
                tanggal_akhir__gte=tanggal,
                is_tutup=True,
            ).first()
            if closed_period:
                self.add_error('tanggal', f'Tanggal ini berada pada periode {closed_period.nama} yang sudah ditutup.')

        return cleaned_data


class JurnalLineForm(forms.ModelForm):
    """Form untuk satu baris jurnal line."""
    class Meta:
        model = JurnalLine
        fields = ['akun', 'debit', 'kredit', 'keterangan']
        widgets = {
            'akun': forms.Select(attrs={'class': 'form-select akun-select'}),
            'debit': forms.NumberInput(attrs={'class': 'form-control text-end debit-input', 'min': '0', 'step': '0.01', 'placeholder': '0'}),
            'kredit': forms.NumberInput(attrs={'class': 'form-control text-end kredit-input', 'min': '0', 'step': '0.01', 'placeholder': '0'}),
            'keterangan': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Keterangan baris'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['akun'].queryset = Akun.objects.filter(is_active=True).order_by('kode')
        self.fields['akun'].empty_label = 'Pilih Akun'
        self.fields['keterangan'].required = False


# Inline formset untuk JurnalLine di dalam JurnalEntry
JurnalLineFormSet = inlineformset_factory(
    JurnalEntry,
    JurnalLine,
    form=JurnalLineForm,
    extra=4,
    can_delete=True,
    min_num=2,
    validate_min=True,
)
