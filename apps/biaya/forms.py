"""
==========================================================================
 BIAYA FORMS - Form Kategori Biaya & Transaksi Biaya
==========================================================================
 1. KategoriBiayaForm → Form CRUD kategori biaya (nama, deskripsi, aktif)
 2. TransaksiBiayaForm → Form catat pengeluaran biaya

 Fitur TransaksiBiayaForm:
 - Tanggal default ke hari ini (untuk record baru)
 - Dropdown kategori: hanya aktif, fallback ke semua jika tidak ada
 - Metode pembayaran: dari model MetodePembayaran (shared dengan POS)
 - Upload bukti (foto/PDF) untuk lampiran
==========================================================================
"""

# Import dari framework Django
from django import forms
# Import dari modul internal proyek
from apps.biaya.models import KategoriBiaya, TransaksiBiaya
# Import dari modul internal proyek
from apps.pos.models import MetodePembayaran
# Import dari modul internal proyek
from apps.produk.models import Gudang
from datetime import date


class KategoriBiayaForm(forms.ModelForm):
    """Form CRUD Kategori Biaya."""
    class Meta:
        """Konfigurasi metadata model untuk Django."""
        model = KategoriBiaya
        fields = ['nama', 'deskripsi', 'akun_beban', 'aktif']
        # Widget HTML untuk setiap field form (class CSS, placeholder, dll)
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'form-control'}),
            'deskripsi': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'akun_beban': forms.Select(attrs={'class': 'form-select'}),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter akun_beban: hanya akun bertipe Beban (kode 6-xxxx atau 7-xxxx)
        from apps.akuntansi.models import Akun
        self.fields['akun_beban'].queryset = Akun.objects.filter(
            is_active=True, tipe__in=['beban', 'hpp']
        ).order_by('kode')
        self.fields['akun_beban'].empty_label = 'Pilih Akun Beban (Opsional — default: 6-9000)'
        self.fields['akun_beban'].required = False


class TransaksiBiayaForm(forms.ModelForm):
    """
    Form catat pengeluaran biaya.
    
    Fitur khusus:
    - Default tanggal = hari ini (hanya untuk record baru)
    - Kategori dropdown: prioritas aktif, fallback ke semua
    - Metode pembayaran: shared model dari apps.pos (MetodePembayaran)
    - Cabang: pilih gudang/cabang untuk biaya ini
    - Bukti: upload file (foto/PDF) sebagai lampiran
    """
    class Meta:
        """Konfigurasi metadata model untuk Django."""
        model = TransaksiBiaya
        fields = ['tanggal', 'kategori', 'cabang', 'jumlah', 'metode_pembayaran', 'deskripsi', 'bukti']
        # Widget HTML untuk setiap field form (class CSS, placeholder, dll)
        widgets = {
            'tanggal': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'kategori': forms.Select(attrs={'class': 'form-select'}),
            'cabang': forms.Select(attrs={'class': 'form-select'}),
            'jumlah': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'metode_pembayaran': forms.Select(attrs={'class': 'form-select'}),
            'deskripsi': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'bukti': forms.FileInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'tanggal': 'Tanggal Transaksi',
            'kategori': 'Kategori Biaya',
            'cabang': 'Cabang',
            'jumlah': 'Jumlah (Rp)',
            'metode_pembayaran': 'Metode Pembayaran',
            'deskripsi': 'Deskripsi/Keterangan',
            'bukti': 'Upload Bukti (Foto/PDF)',
        }
    
    def __init__(self, *args, **kwargs):
        """Inisialisasi form — konfigurasi field dan widget."""
        super().__init__(*args, **kwargs)
        # Dropdown kategori: prioritas aktif, fallback ke semua jika kosong
        active_kategori = KategoriBiaya.objects.filter(aktif=True)
        if active_kategori.exists():
            # Set queryset dropdown kategori
            self.fields['kategori'].queryset = active_kategori
        else:
            # Query database — ambil semua data self.fields['kategori'].queryset
            # Set queryset dropdown kategori
            self.fields['kategori'].queryset = KategoriBiaya.objects.all()
        self.fields['kategori'].empty_label = 'Pilih Kategori Biaya'
        
        # Metode pembayaran hanya yang aktif
        self.fields['metode_pembayaran'].queryset = MetodePembayaran.objects.filter(aktif=True)
        self.fields['metode_pembayaran'].empty_label = 'Pilih Metode Pembayaran (Opsional)'
        
        # Cabang/gudang hanya yang aktif
        self.fields['cabang'].queryset = Gudang.objects.filter(aktif=True)
        self.fields['cabang'].empty_label = 'Pilih Cabang (Opsional)'
        
        # Default tanggal ke hari ini untuk record baru
        if not self.instance.pk:
            self.fields['tanggal'].initial = date.today()
