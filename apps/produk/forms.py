"""
==========================================================================
 PRODUK FORMS - Form Django untuk Produk
==========================================================================
 File ini berisi ProdukForm — form untuk menambah dan mengedit produk.

 Apa itu ModelForm?
 - Form yang otomatis di-generate dari Model Django
 - Field form = field model, validasi otomatis
 - form.save() langsung menyimpan ke database

 Kustomisasi di form ini:
 - widgets: Atribut HTML untuk setiap field (class CSS, placeholder, ID)
 - __init__: Override field properties (required, label)

 Koneksi:
 - apps/produk/models.py → Produk model
 - apps/produk/views.py → ProdukCreateView, ProdukUpdateView
 - templates/produk/produk_form.html → Render form ini
==========================================================================
"""

# Import dari framework Django
from django import forms                                    # Django forms framework
# Import dari modul internal proyek
from apps.produk.models import Produk, Kategori, Satuan, Gudang  # Model terkait


class ProdukForm(forms.ModelForm):
    """
    Form untuk menambah dan mengedit produk.
    Menggunakan ModelForm → field otomatis dari model Produk.

    Widgets:
    - TextInput → Input teks biasa (SKU, nama, barcode)
    - Select → Dropdown pilihan (kategori, satuan, cabang)
    - NumberInput → Input angka (harga beli, harga jual)
    - Textarea → Input teks panjang (deskripsi)
    - FileInput → Upload file (gambar)
    - CheckboxInput → Checkbox (aktif/tidak)
    """

    # Konfigurasi metadata model/form
    class Meta:
        """Konfigurasi form Produk — field dan widget termasuk Select2 dropdown."""
        model = Produk  # Form berdasarkan model Produk
        # Field yang ditampilkan di form (urutan sesuai tampilan)
        fields = ['sku', 'barcode', 'nama', 'kategori', 'satuan', 'cabang',
                  'harga_beli', 'harga_jual', 'deskripsi', 'gambar', 'aktif', 'kena_ppn', 'metode_pembayaran']

        # Kustomisasi widget HTML untuk setiap field
        widgets = {
            'sku': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'SKU (Auto-generated jika kosong)',
                'id': 'productSKU'
            }),
            'barcode': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Barcode (Opsional)',
                'id': 'productBarcode'
            }),
            'nama': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nama Produk',
                'id': 'productName',
                'required': True
            }),
            'kategori': forms.Select(attrs={
                'class': 'select2 form-select form-select-lg',  # Select2 dropdown
                'id': 'productCategory',
                'data-allow-clear': 'true'  # Select2: bisa clear pilihan
            }),
            'satuan': forms.Select(attrs={
                'class': 'select2 form-select form-select-lg',
                'id': 'productUnit',
                'data-allow-clear': 'true'
            }),
            'cabang': forms.Select(attrs={
                'class': 'select2 form-select form-select-lg',
                'id': 'productCabang',
                'data-allow-clear': 'true'
            }),
            'harga_beli': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0',
                'id': 'harga_beli',
                'min': '0',
                'step': '0.01'  # Bisa input desimal
            }),
            'harga_jual': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0',
                'id': 'harga_jual',
                'min': '0',
                'step': '0.01'
            }),
            'deskripsi': forms.Textarea(attrs={
                'class': 'form-control h-px-100',
                'placeholder': 'Deskripsi produk...',
                'id': 'deskripsi',
                'rows': 4
            }),
            'gambar': forms.FileInput(attrs={
                'class': 'form-control',
                'id': 'formFile',
                'accept': 'image/*'  # Hanya terima file gambar
            }),
            'aktif': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'productActive'
            }),
            'kena_ppn': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'productKenaPPN'
            }),
            'metode_pembayaran': forms.Select(attrs={
                'class': 'form-select',
                'id': 'productMetodePembayaran'
            })
        }

    def __init__(self, *args, **kwargs):
        """
        Override konstruktor untuk mengatur field properties.

        Di sini kita:
        - Set field opsional (required=False)
        - Set label dalam Bahasa Indonesia
        """
        super().__init__(*args, **kwargs)

        # Field yang TIDAK wajib diisi
        self.fields['sku'].required = False       # Auto-generate jika kosong
        # Set field barcode sebagai opsional/wajib
        self.fields['barcode'].required = False
        # Set field deskripsi sebagai opsional/wajib
        self.fields['deskripsi'].required = False
        # Set field gambar sebagai opsional/wajib
        self.fields['gambar'].required = False
        # Set field cabang sebagai opsional/wajib
        self.fields['cabang'].required = False

        # Label dalam Bahasa Indonesia
        self.fields['sku'].label = 'SKU'
        # Set label field barcode dalam Bahasa Indonesia
        self.fields['barcode'].label = 'Barcode'
        # Set label field nama dalam Bahasa Indonesia
        self.fields['nama'].label = 'Nama Produk'
        # Set label field kategori dalam Bahasa Indonesia
        self.fields['kategori'].label = 'Kategori'
        # Set label field satuan dalam Bahasa Indonesia
        self.fields['satuan'].label = 'Satuan'
        # Set label field cabang dalam Bahasa Indonesia
        self.fields['cabang'].label = 'Cabang'
        # Set label field harga_beli dalam Bahasa Indonesia
        self.fields['harga_beli'].label = 'Harga Beli'
        # Set label field harga_jual dalam Bahasa Indonesia
        self.fields['harga_jual'].label = 'Harga Jual'
        # Set label field deskripsi dalam Bahasa Indonesia
        self.fields['deskripsi'].label = 'Deskripsi'
        # Set label field gambar dalam Bahasa Indonesia
        self.fields['gambar'].label = 'Gambar Produk'
        # Set label field aktif dalam Bahasa Indonesia
        self.fields['aktif'].label = 'Produk Aktif'
        # Set label field kena_ppn
        self.fields['kena_ppn'].label = 'Kena PPN'
        # Set field metode_pembayaran sebagai opsional
        self.fields['metode_pembayaran'].required = False
        self.fields['metode_pembayaran'].label = 'Metode Pembayaran'
