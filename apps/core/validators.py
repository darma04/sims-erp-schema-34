"""
==========================================================================
 CORE VALIDATORS - Validasi Bisnis Terpusat
==========================================================================
 File ini berisi fungsi validasi yang digunakan lintas modul:

 1. validate_metode_pembayaran_mapping() → Validasi kelengkapan mapping
    MetodePembayaran ke Kas/Bank dan Akun CoA sebelum transaksi diproses.

 2. validate_akun_beban_type() → Validasi bahwa akun yang di-assign ke
    KategoriBiaya bertipe Beban (kode 6-xxxx atau 7-xxxx).

 3. validate_master_data_deactivation() → Validasi sebelum menonaktifkan
    master data (MetodePembayaran/Supplier/Customer) — cek apakah ada
    dokumen draft/submitted yang masih menggunakan entitas tersebut.

 Semua fungsi menggunakan lazy import untuk menghindari circular imports.
==========================================================================
"""

from django.core.exceptions import ValidationError


def validate_metode_pembayaran_mapping(metode_pembayaran):
    """
    Validasi bahwa MetodePembayaran memiliki mapping Kas/Bank yang lengkap dan aktif.

    Dipanggil sebelum transisi status yang memicu pembuatan jurnal:
    - SO → confirmed
    - PO → received
    - POS → paid
    - Biaya → approved
    - Penggajian → dibayar

    Parameters:
        metode_pembayaran: Instance MetodePembayaran yang akan divalidasi.

    Raises:
        ValidationError: Jika metode_pembayaran None, atau mapping tidak lengkap/tidak aktif.
    """
    # Cek apakah metode pembayaran sudah dipilih
    if metode_pembayaran is None:
        raise ValidationError("Metode pembayaran belum dipilih.")

    from apps.kas_bank.services import metode_is_credit
    if metode_is_credit(metode_pembayaran):
        return

    # Cek kas_bank_account terisi dan aktif
    kas_bank_account = metode_pembayaran.kas_bank_account
    akun_kas_bank = metode_pembayaran.akun_kas_bank

    is_valid = True

    # Validasi kas_bank_account: harus terisi dan aktif
    if kas_bank_account is None or not kas_bank_account.aktif:
        is_valid = False

    # Validasi akun_kas_bank (Akun CoA): harus terisi dan aktif
    if akun_kas_bank is None or not akun_kas_bank.is_active:
        is_valid = False

    if not is_valid:
        raise ValidationError(
            f"MetodePembayaran '{metode_pembayaran.nama}' belum memiliki mapping "
            f"Kas/Bank yang valid. Silakan lengkapi di menu Pengaturan > Metode Pembayaran."
        )


def validate_akun_beban_type(akun):
    """
    Validasi bahwa akun yang di-assign ke KategoriBiaya bertipe Beban.

    Akun beban harus memiliki kode yang dimulai dengan '6-' atau '7-':
    - 6-xxxx = Beban Operasional
    - 7-xxxx = Beban Lain-lain

    Parameters:
        akun: Instance Akun yang akan divalidasi, atau None.

    Returns:
        None jika akun is None (allow NULL — backward compatible).

    Raises:
        ValidationError: Jika akun bukan bertipe Beban.
    """
    # Allow NULL — KategoriBiaya.akun_beban boleh kosong (fallback ke 6-9000)
    if akun is None:
        return

    # Cek kode akun dimulai dengan '6-' atau '7-' (tipe beban)
    kode = akun.kode or ''
    if not (kode.startswith('6-') or kode.startswith('7-')):
        raise ValidationError(
            f"Akun beban harus bertipe Beban (kode 6-xxxx atau 7-xxxx). "
            f"Akun '{akun.kode} - {akun.nama}' tidak valid."
        )


def validate_master_data_deactivation(instance, model_type):
    """
    Validasi sebelum menonaktifkan master data.

    Cek apakah ada dokumen transaksi berstatus draft/submitted yang masih
    menggunakan entitas ini. Jika ada, kembalikan daftar dokumen terdampak
    sebagai warning (bukan hard block — user tetap bisa memutuskan).

    Parameters:
        instance: Instance model yang akan dinonaktifkan.
        model_type: Tipe model — 'metode_pembayaran', 'supplier', atau 'customer'.

    Returns:
        list: Daftar string deskripsi dokumen terdampak.
              Kosong jika tidak ada dokumen yang terpengaruh.
    """
    affected_documents = []

    if model_type == 'metode_pembayaran':
        # Cek TransaksiBiaya draft/submitted yang menggunakan metode ini
        from apps.biaya.models import TransaksiBiaya
        biaya_qs = TransaksiBiaya.objects.filter(
            metode_pembayaran=instance,
            status__in=['draft', 'submitted']
        ).values_list('nomor_transaksi', flat=True)[:20]

        for nomor in biaya_qs:
            affected_documents.append(f"Transaksi Biaya: {nomor}")

        # Cek PurchaseOrder draft/submitted yang menggunakan metode ini
        from apps.pembelian.models import PurchaseOrder
        po_qs = PurchaseOrder.objects.filter(
            metode_pembayaran=instance,
            status__in=['draft', 'submitted']
        ).values_list('nomor_po', flat=True)[:20]

        for nomor in po_qs:
            affected_documents.append(f"Purchase Order: {nomor}")

        # Cek SalesOrder draft yang menggunakan metode ini
        from apps.penjualan.models import SalesOrder
        so_qs = SalesOrder.objects.filter(
            metode_pembayaran=instance,
            status='draft'
        ).values_list('nomor_so', flat=True)[:20]

        for nomor in so_qs:
            affected_documents.append(f"Sales Order: {nomor}")

        # Cek POSTransaction draft yang menggunakan metode ini
        from apps.pos.models import POSTransaction
        pos_qs = POSTransaction.objects.filter(
            metode_pembayaran=instance,
            status__in=['draft', 'submitted']
        ).values_list('nomor_transaksi', flat=True)[:20]

        for nomor in pos_qs:
            affected_documents.append(f"Transaksi POS: {nomor}")

    elif model_type == 'supplier':
        # Cek PurchaseOrder draft yang menggunakan supplier ini
        from apps.pembelian.models import PurchaseOrder
        po_qs = PurchaseOrder.objects.filter(
            supplier=instance,
            status='draft'
        ).values_list('nomor_po', flat=True)[:20]

        for nomor in po_qs:
            affected_documents.append(f"Purchase Order: {nomor}")

    elif model_type == 'customer':
        # Cek SalesOrder draft yang menggunakan customer ini
        from apps.penjualan.models import SalesOrder
        so_qs = SalesOrder.objects.filter(
            customer=instance,
            status='draft'
        ).values_list('nomor_so', flat=True)[:20]

        for nomor in so_qs:
            affected_documents.append(f"Sales Order: {nomor}")

    return affected_documents


import os

def validate_file_size(max_mb):
    def validator(file):
        limit = max_mb * 1024 * 1024
        if file.size > limit:
            raise ValidationError(f"Ukuran file tidak boleh melebihi {max_mb}MB.")
    return validator

def validate_image_file(file):
    if not file:
        return
    ext = os.path.splitext(file.name)[1].lower()
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico']
    if ext not in valid_extensions:
        raise ValidationError(f"Ekstensi file '{ext}' tidak diizinkan. Gunakan format gambar yang valid: {', '.join(valid_extensions)}")
    
    # Validasi ukuran (max 5MB)
    validate_file_size(5)(file)

def validate_document_file(file):
    if not file:
        return
    ext = os.path.splitext(file.name)[1].lower()
    valid_extensions = ['.pdf', '.xlsx', '.xls', '.csv', '.doc', '.docx']
    if ext not in valid_extensions:
        raise ValidationError(f"Ekstensi file '{ext}' tidak diizinkan. Gunakan format dokumen yang valid: {', '.join(valid_extensions)}")
    
    # Validasi ukuran (max 10MB)
    validate_file_size(10)(file)

def validate_expense_proof(file):
    if not file:
        return
    ext = os.path.splitext(file.name)[1].lower()
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.pdf']
    if ext not in valid_extensions:
        raise ValidationError(f"Ekstensi file '{ext}' tidak diizinkan. Gunakan format gambar atau PDF yang valid: {', '.join(valid_extensions)}")
    
    # Validasi ukuran (max 10MB)
    validate_file_size(10)(file)


