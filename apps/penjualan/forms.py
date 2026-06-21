"""
==========================================================================
 PENJUALAN FORMS - Form Customer, SO, dan SO Items Formset
==========================================================================
 File ini berisi:
 1. CustomerForm → Form CRUD customer
 2. SalesOrderForm → Form utama SO (customer, gudang, tanggal, dll)
 3. SalesOrderItemForm → Form per-item SO (produk, jumlah, harga, diskon)
 4. SalesOrderItemFormSet → Formset items SO

 Perbedaan dengan PO Forms:
 - SO punya field 'diskon' per-item (PO tidak)
 - SO menggunakan produk existing (PO bisa buat produk baru)
==========================================================================
"""

# Import dari framework Django
from django import forms
# Import dari framework Django
from django.forms import inlineformset_factory
# Import dari modul internal proyek
from apps.penjualan.models import Customer, SalesOrder, SalesOrderItem
# Import dari modul internal proyek
from apps.produk.models import Gudang, Produk, Satuan


class CustomerForm(forms.ModelForm):
    """
    Form CRUD Customer.
    Fields: kode, nama, telepon, email, alamat, aktif
    """
    
    # Konfigurasi metadata model/form
    class Meta:
        """Konfigurasi form Customer — field identitas dan kontak."""
        model = Customer
        fields = ['kode', 'nama', 'telepon', 'email', 'alamat', 'aktif']
        # Widget HTML untuk setiap field form (class CSS, placeholder, dll)
        widgets = {
            'kode': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'CUST-001'}),
            'nama': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nama Customer'}),
            'telepon': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '021-12345678'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@customer.com'}),
            'alamat': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Alamat Customer'}),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class SalesOrderForm(forms.ModelForm):
    """
    Form utama SALES ORDER.
    
    Fitur:
    - nomor_so bisa auto-generate jika dikosongkan
    - tanggal menggunakan datetime-local widget
    - diskon dan pajak level header (bukan per-item)
    - Customer dan gudang dropdown hanya yg aktif
    - Metode pembayaran untuk tracking saldo
    """
    
    # Konfigurasi metadata model/form
    class Meta:
        """Konfigurasi form SalesOrder — field utama SO termasuk diskon dan pajak."""
        model = SalesOrder
        fields = ['nomor_so', 'tanggal', 'customer', 'gudang', 'metode_pembayaran', 'status', 'catatan', 'diskon', 'pajak', 'biaya_pengiriman']
        # Widget HTML untuk setiap field form (class CSS, placeholder, dll)
        widgets = {
            'nomor_so': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Auto-generate jika kosong'}),
            'tanggal': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'customer': forms.Select(attrs={'class': 'form-select select2'}),
            'gudang': forms.Select(attrs={'class': 'form-select select2'}),
            'metode_pembayaran': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'catatan': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'diskon': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0', 'min': '0', 'step': '0.01'}),
            'pajak': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0', 'min': '0', 'step': '0.01'}),
            'biaya_pengiriman': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0', 'min': '0', 'step': '0.01'}),
        }
    
    def __init__(self, *args, **kwargs):
        """Inisialisasi form — filter dropdown aktif, set label Indonesia, format tanggal edit."""
        super().__init__(*args, **kwargs)
        # Filter dropdown → hanya data aktif
        self.fields['customer'].queryset = Customer.objects.filter(aktif=True)
        # Query database — ambil data self.fields['gudang'].queryset yang sesuai filter
        # Set queryset dropdown gudang
        self.fields['gudang'].queryset = Gudang.objects.filter(aktif=True)
        
        # Filter metode pembayaran → hanya yang aktif
        from apps.pos.models import MetodePembayaran
        # Query database — ambil data self.fields['metode_pembayaran'].queryset yang sesuai filter
        # Set queryset dropdown metode_pembayaran
        self.fields['metode_pembayaran'].queryset = MetodePembayaran.objects.filter(aktif=True)
        if not self.instance.pk:
            metode_tempo = MetodePembayaran.objects.filter(
                aktif=True, kode__in=['TEMPO', 'KREDIT', 'CREDIT']
            ).order_by('kode').first()
            if metode_tempo:
                self.initial['metode_pembayaran'] = metode_tempo.pk
        
        # nomor_so opsional — boleh dikosongkan agar auto-generate via SalesOrder.save()
        # (model field unique=True secara default membuat form field required, padahal kita mau kosong)
        self.fields['nomor_so'].required = False

        # Label Indonesia
        self.fields['nomor_so'].label = 'Nomor SO'
        # Set label field tanggal dalam Bahasa Indonesia
        self.fields['tanggal'].label = 'Tanggal'
        # Set label field customer dalam Bahasa Indonesia
        self.fields['customer'].label = 'Customer'
        # Set label field gudang dalam Bahasa Indonesia
        self.fields['gudang'].label = 'Gudang'
        # Set label field metode_pembayaran dalam Bahasa Indonesia
        self.fields['metode_pembayaran'].label = 'Metode Pembayaran'
        # Set label field status dalam Bahasa Indonesia
        self.fields['status'].label = 'Status'
        # Set label field catatan dalam Bahasa Indonesia
        self.fields['catatan'].label = 'Catatan'
        # Set label field diskon dalam Bahasa Indonesia
        self.fields['diskon'].label = 'Diskon (Rp)'
        # Set label field pajak dalam Bahasa Indonesia
        self.fields['pajak'].label = 'Pajak (Rp)'
        self.fields['biaya_pengiriman'].label = 'Biaya Pengiriman/Ongkir (Rp)'
        
        # Placeholder dropdown kosong
        self.fields['customer'].empty_label = 'Pilih Customer'
        self.fields['gudang'].empty_label = 'Pilih Gudang'
        self.fields['metode_pembayaran'].empty_label = 'Kredit/Tempo (default jika kosong)'
        
        # Format tanggal saat edit (datetime-local format: YYYY-MM-DDThh:mm)
        if self.instance and self.instance.pk and self.instance.tanggal:
            self.initial['tanggal'] = self.instance.tanggal.strftime('%Y-%m-%dT%H:%M')


class SalesOrderItemForm(forms.ModelForm):
    """
    Form per-item SO — pilih produk existing, jumlah, harga, diskon.
    Digunakan dalam SalesOrderItemFormSet.
    """
    
    # Konfigurasi metadata model/form
    class Meta:
        """Konfigurasi form item SO — field produk, jumlah, harga, diskon, satuan_transaksi, catatan."""
        model = SalesOrderItem
        fields = ['produk', 'jumlah', 'harga_satuan', 'diskon', 'satuan_transaksi', 'catatan']
        # Widget HTML untuk setiap field form (class CSS, placeholder, dll)
        widgets = {
            'produk': forms.Select(attrs={'class': 'form-select select2-item'}),
            'jumlah': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'harga_satuan': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'diskon': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
            'satuan_transaksi': forms.Select(attrs={'class': 'form-select'}),
            'catatan': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        """Inisialisasi form — filter dropdown produk aktif saja."""
        super().__init__(*args, **kwargs)
        # Query database — ambil data self.fields['produk'].queryset yang sesuai filter
        # Set queryset dropdown produk
        self.fields['produk'].queryset = Produk.objects.filter(aktif=True)
        self.fields['produk'].empty_label = 'Pilih Produk'


# ============================================================
# FORMSET — Items SO (inline formset)
# ============================================================
SalesOrderItemFormSet = inlineformset_factory(
    SalesOrder,              # Parent model
    SalesOrderItem,          # Child model
    form=SalesOrderItemForm,
    fields=['produk', 'jumlah', 'harga_satuan', 'diskon', 'satuan_transaksi', 'catatan'],
    extra=1,                 # 1 form kosong extra
    can_delete=True,         # Bisa hapus item
    widgets={
        'produk': forms.Select(attrs={'class': 'form-select select2-item'}),
        'jumlah': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
        'harga_satuan': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
        'diskon': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}),
        'satuan_transaksi': forms.Select(attrs={'class': 'form-select'}),
        'catatan': forms.TextInput(attrs={'class': 'form-control'}),
    }
)
