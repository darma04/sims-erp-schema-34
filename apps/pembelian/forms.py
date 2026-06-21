"""
==========================================================================
 PEMBELIAN FORMS - Form Supplier, PO, dan PO Items Formset
==========================================================================
 File ini berisi:
 1. SupplierForm → Form CRUD supplier
 2. PurchaseOrderForm → Form utama PO (supplier, gudang, tanggal, dll)
 3. PurchaseOrderItemFormSet → Formset untuk items PO (edit mode)
 4. PurchaseOrderItemForm → Form per-item PO

 Catatan: PO CREATE tidak menggunakan formset standar, melainkan
 POST data manual (lihat PurchaseOrderCreateView.form_valid())
==========================================================================
"""

# Import dari framework Django
from django import forms
# Import dari modul internal proyek
from apps.pembelian.models import Supplier, PurchaseOrder, PurchaseOrderItem
# Import dari modul internal proyek
from apps.produk.models import Gudang, Produk
# Import dari modul internal proyek
from apps.pos.models import MetodePembayaran


class SupplierForm(forms.ModelForm):
    """
    Form untuk CRUD Supplier.
    Fields: kode, nama, kontak, telepon, email, alamat, aktif
    Semua widget menggunakan Bootstrap 5 classes.
    """
    
    # Konfigurasi metadata model/form
    class Meta:
        """Konfigurasi form Supplier — field identitas dan kontak."""
        model = Supplier
        fields = ['kode', 'nama', 'kontak', 'telepon', 'email', 'alamat', 'aktif']
        # Widget HTML untuk setiap field form (class CSS, placeholder, dll)
        widgets = {
            'kode': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'SUP-001'}),
            'nama': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nama Supplier'}),
            'kontak': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nama Kontak Person'}),
            'telepon': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '021-12345678'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@supplier.com'}),
            'alamat': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Alamat Supplier'}),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class PurchaseOrderForm(forms.ModelForm):
    """
    Form utama PURCHASE ORDER.
    
    Fitur khusus:
    - Field tanggal menggunakan DateTimeInput type='datetime-local'
    - Dropdown supplier, gudang, metode_pembayaran hanya tampilkan yang aktif
    - Nomor PO bisa diisi manual atau auto-generate
    - Tanggal di-format ke 'datetime-local' saat edit
    """
    
    # Override field tanggal untuk widget HTML5 datetime-local
    tanggal = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
        label='Tanggal PO',
        required=False  # Auto-set jika tidak diisi
    )
    
    # Konfigurasi metadata model/form
    class Meta:
        """Konfigurasi form PurchaseOrder — field utama PO termasuk pajak dan metode bayar."""
        model = PurchaseOrder
        fields = ['nomor_po', 'tanggal', 'supplier', 'gudang', 'metode_pembayaran', 'status', 'catatan', 'pajak', 'biaya_pengiriman']
        # Widget HTML untuk setiap field form (class CSS, placeholder, dll)
        widgets = {
            'nomor_po': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Auto-generate jika kosong'}),
            'supplier': forms.Select(attrs={'class': 'form-select select2'}),
            'gudang': forms.Select(attrs={'class': 'form-select select2'}),
            'metode_pembayaran': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'catatan': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'pajak': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0', 'min': '0', 'step': '0.01'}),
            'biaya_pengiriman': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0', 'min': '0', 'step': '0.01'}),
        }
    
    def __init__(self, *args, **kwargs):
        """Inisialisasi form — filter dropdown aktif, set label Indonesia, format tanggal edit."""
        super().__init__(*args, **kwargs)
        # Filter dropdown hanya data aktif
        self.fields['supplier'].queryset = Supplier.objects.filter(aktif=True)
        # Query database — ambil data self.fields['gudang'].queryset yang sesuai filter
        # Set queryset dropdown gudang
        self.fields['gudang'].queryset = Gudang.objects.filter(aktif=True)
        # Query database — ambil data self.fields['metode_pembayaran'].queryset yang sesuai filter
        # Set queryset dropdown metode_pembayaran
        self.fields['metode_pembayaran'].queryset = MetodePembayaran.objects.filter(aktif=True)
        
        # Set label Indonesia
        self.fields['nomor_po'].label = 'Nomor PO'
        # Set label field tanggal dalam Bahasa Indonesia
        self.fields['tanggal'].label = 'Tanggal'
        # Set label field supplier dalam Bahasa Indonesia
        self.fields['supplier'].label = 'Supplier'
        # Set label field gudang dalam Bahasa Indonesia
        self.fields['gudang'].label = 'Gudang Tujuan'
        # Set label field metode_pembayaran dalam Bahasa Indonesia
        self.fields['metode_pembayaran'].label = 'Metode Pembayaran'
        # Set label field status dalam Bahasa Indonesia
        self.fields['status'].label = 'Status'
        # Set label field catatan dalam Bahasa Indonesia
        self.fields['catatan'].label = 'Catatan'
        # Set label field pajak dalam Bahasa Indonesia
        self.fields['pajak'].label = 'Pajak (Rp)'
        self.fields['biaya_pengiriman'].label = 'Biaya Pengiriman/Ongkir (Rp)'
        
        # Set placeholder pada dropdown kosong
        self.fields['supplier'].empty_label = 'Pilih Supplier'
        self.fields['gudang'].empty_label = 'Pilih Gudang'
        self.fields['metode_pembayaran'].empty_label = 'Kredit/Tempo (default jika kosong)'
        
        # Format tanggal untuk edit mode (datetime-local format)
        if self.instance and self.instance.pk and self.instance.tanggal:
            # Import dari framework Django
            from django.utils import timezone
            local_time = timezone.localtime(self.instance.tanggal)
            self.initial['tanggal'] = local_time.strftime('%Y-%m-%dT%H:%M')


# ============================================================
# FORMSET — Kumpulan form items PO (untuk mode EDIT)
# ============================================================
from django.forms import inlineformset_factory

PurchaseOrderItemFormSet = inlineformset_factory(
    PurchaseOrder,           # Parent model
    PurchaseOrderItem,       # Child model
    fields=['produk', 'jumlah', 'harga_satuan', 'satuan_transaksi', 'catatan'],
    extra=1,                 # 1 form kosong extra untuk tambah item baru
    can_delete=True,         # Bisa hapus item
    widgets={
        'produk': forms.Select(attrs={'class': 'form-select select2-item'}),
        'jumlah': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        'harga_satuan': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        'satuan_transaksi': forms.Select(attrs={'class': 'form-select form-select-sm'}),
        'catatan': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional'}),
    }
)


class PurchaseOrderItemForm(forms.ModelForm):
    """
    Form per-item PO (standalone, bukan dalam formset).
    Digunakan jika perlu form item tunggal di tempat lain.
    """
    
    # Konfigurasi metadata model/form
    class Meta:
        """Konfigurasi form item PO — field produk, jumlah, harga, satuan_transaksi, catatan."""
        model = PurchaseOrderItem
        fields = ['produk', 'jumlah', 'harga_satuan', 'satuan_transaksi', 'catatan']
        # Widget HTML untuk setiap field form (class CSS, placeholder, dll)
        widgets = {
            'produk': forms.Select(attrs={'class': 'form-select select2'}),
            'jumlah': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'harga_satuan': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'satuan_transaksi': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'catatan': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        """Inisialisasi form — filter dropdown produk aktif saja."""
        super().__init__(*args, **kwargs)
        # Query database — ambil data self.fields['produk'].queryset yang sesuai filter
        # Set queryset dropdown produk
        self.fields['produk'].queryset = Produk.objects.filter(aktif=True)
        self.fields['produk'].empty_label = 'Pilih Produk'
