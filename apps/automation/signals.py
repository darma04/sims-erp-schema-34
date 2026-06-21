"""
==========================================================================
 AUTOMATION SIGNALS - Helper Notifikasi Telegram per Jenis Transaksi
==========================================================================
 File ini berisi fungsi-fungsi helper yang menyiapkan data notifikasi
 dan mengirimnya ke Telegram. Disebut "signals" karena awalnya dirancang
 sebagai signal handler, tapi sekarang DIPANGGIL LANGSUNG dari views.

 Alasan dipanggil dari views, bukan dari post_save signal:
 - Saat post_save terpicu, items transaksi belum tersimpan
 - Kita butuh data lengkap (items + total) sebelum kirim notifikasi
 - Jadi fungsi ini dipanggil SETELAH semua items disimpan di views

 Fungsi yang tersedia:
 ┌───────────────────────────────────┬──────────────────────────────────────┐
 │ Fungsi                            │ Dipanggil dari                       │
 ├───────────────────────────────────┼──────────────────────────────────────┤
 │ kirim_notifikasi_pos()            │ pos/views.py setelah transaksi POS   │
 │ kirim_notifikasi_sales_order()    │ penjualan/views.py setelah SO dibuat │
 │ kirim_notifikasi_purchase_order() │ pembelian/views.py setelah PO dibuat │
 │ kirim_notifikasi_biaya()          │ biaya/views.py setelah biaya dibuat  │
 │ kirim_notifikasi_penggajian()     │ hr/views.py setelah gaji dibuat      │
 └───────────────────────────────────┴──────────────────────────────────────┘

 Setiap fungsi mengikuti pola yang sama:
 1. refresh_from_db() → Ambil data terbaru dari database
 2. Format detail items menjadi string untuk pesan
 3. Siapkan dict data sesuai placeholder template
 4. Cek apakah kirim_pdf aktif:
    - Jika YA → kirim PDF+caption (1 pesan gabungan), TANPA pesan teks terpisah
    - Jika TIDAK → kirim pesan teks biasa saja

 Terhubung dengan:
 - telegram_service.py → kirim_notifikasi_async(), kirim_dokumen_async(), format_angka()
 - pdf_generator.py → generate_*_pdf() untuk membuat file PDF
 - views.py (pos, penjualan, pembelian, biaya, hr) → Memanggil fungsi di sini
 - models.py → TemplatePesan (template pesan diambil dari database)
==========================================================================
"""

# Import fungsi dari telegram_service.py:
from .telegram_service import kirim_notifikasi_async, kirim_dokumen_async, format_angka


def _is_kirim_pdf_aktif():
    """Cek apakah fitur kirim Telegram aktif. Sesuai request, PDF selalu dikirim."""
    try:
        from .models import PengaturanTelegram
        pengaturan = PengaturanTelegram.load()
        # Selalu return True untuk PDF jika telegram aktif keseluruhan
        return pengaturan.aktif
    except Exception:
        return False


def kirim_notifikasi_pos(instance):
    """
    Kirim notifikasi Telegram untuk transaksi POS yang baru selesai.
    Jika kirim_pdf aktif: kirim PDF dengan caption template (1 pesan).
    Jika tidak: kirim teks notifikasi saja.
    """
    instance.refresh_from_db()

    items = instance.items.all()
    detail_items = ""
    for i, item in enumerate(items, 1):
        detail_items += f"  {i}. {item.produk.nama} x{item.jumlah} = Rp {format_angka(item.subtotal)}\n"

    if not detail_items:
        detail_items = "  (Belum ada item)"

    data = {
        'nomor_transaksi': instance.nomor_transaksi,
        'tanggal': instance.tanggal.strftime('%d/%m/%Y %H:%M') if instance.tanggal else '-',
        'kasir': instance.kasir.get_full_name() or instance.kasir.username if instance.kasir else '-',
        'gudang': str(instance.gudang) if instance.gudang else '-',
        'detail_items': detail_items.strip(),
        'subtotal': format_angka(instance.subtotal),
        'diskon': format_angka(instance.diskon),
        'pajak': format_angka(instance.pajak),
        'total': format_angka(instance.total_harga),
        'metode_pembayaran': str(instance.metode_pembayaran) if instance.metode_pembayaran else '-',
        'status': instance.get_status_display() if hasattr(instance, 'get_status_display') else instance.status,
        'customer': instance.nama_customer or 'Walk-in',
    }

    if _is_kirim_pdf_aktif():
        # Kirim PDF dengan teks template sebagai caption (1 pesan gabungan)
        from .pdf_generator import generate_pos_pdf
        kirim_dokumen_async('pos', instance.nomor_transaksi, instance, generate_pos_pdf, data)
    else:
        # Kirim pesan teks saja
        kirim_notifikasi_async('pos', instance.nomor_transaksi, data)


def kirim_notifikasi_sales_order(instance):
    """
    Kirim notifikasi Telegram untuk Sales Order yang baru dibuat.
    Jika kirim_pdf aktif: kirim PDF dengan caption template (1 pesan).
    Jika tidak: kirim teks notifikasi saja.
    """
    instance.refresh_from_db()

    items = instance.items.all()
    detail_items = ""
    for i, item in enumerate(items, 1):
        detail_items += f"  {i}. {item.produk.nama} x{item.jumlah} = Rp {format_angka(item.subtotal)}\n"

    if not detail_items:
        detail_items = "  (Belum ada item)"

    data = {
        'nomor_so': instance.nomor_so,
        'tanggal': instance.tanggal.strftime('%d/%m/%Y %H:%M') if instance.tanggal else '-',
        'customer': str(instance.customer) if instance.customer else '-',
        'gudang': str(instance.gudang) if instance.gudang else '-',
        'detail_items': detail_items.strip(),
        'subtotal': format_angka(instance.subtotal),
        'diskon': format_angka(instance.diskon),
        'pajak': format_angka(instance.pajak),
        'total': format_angka(instance.total_harga),
        'status': instance.get_status_display() if hasattr(instance, 'get_status_display') else instance.status,
        'dibuat_oleh': instance.dibuat_oleh.get_full_name() or instance.dibuat_oleh.username if instance.dibuat_oleh else '-',
    }

    if _is_kirim_pdf_aktif():
        from .pdf_generator import generate_sales_order_pdf
        kirim_dokumen_async('sales_order', instance.nomor_so, instance, generate_sales_order_pdf, data)
    else:
        kirim_notifikasi_async('sales_order', instance.nomor_so, data)


def kirim_notifikasi_purchase_order(instance):
    """
    Kirim notifikasi Telegram untuk Purchase Order yang baru dibuat.
    Jika kirim_pdf aktif: kirim PDF dengan caption template (1 pesan).
    Jika tidak: kirim teks notifikasi saja.
    """
    instance.refresh_from_db()

    items = instance.items.all()
    detail_items = ""
    for i, item in enumerate(items, 1):
        detail_items += f"  {i}. {item.produk.nama} x{item.jumlah} = Rp {format_angka(item.subtotal)}\n"

    if not detail_items:
        detail_items = "  (Belum ada item)"

    data = {
        'nomor_po': instance.nomor_po,
        'tanggal': instance.tanggal.strftime('%d/%m/%Y %H:%M') if instance.tanggal else '-',
        'supplier': str(instance.supplier) if instance.supplier else '-',
        'gudang': str(instance.gudang) if instance.gudang else '-',
        'detail_items': detail_items.strip(),
        'subtotal': format_angka(instance.subtotal),
        'pajak': format_angka(instance.pajak),
        'total': format_angka(instance.total_harga),
        'status': instance.get_status_display() if hasattr(instance, 'get_status_display') else instance.status,
        'dibuat_oleh': instance.dibuat_oleh.get_full_name() or instance.dibuat_oleh.username if instance.dibuat_oleh else '-',
    }

    if _is_kirim_pdf_aktif():
        from .pdf_generator import generate_purchase_order_pdf
        kirim_dokumen_async('purchase_order', instance.nomor_po, instance, generate_purchase_order_pdf, data)
    else:
        kirim_notifikasi_async('purchase_order', instance.nomor_po, data)


def kirim_notifikasi_biaya(instance):
    """
    Kirim notifikasi Telegram untuk Transaksi Biaya yang baru dibuat.
    Jika kirim_pdf aktif: kirim PDF dengan caption template (1 pesan).
    Jika tidak: kirim teks notifikasi saja.
    """
    instance.refresh_from_db()

    data = {
        'nomor_transaksi': instance.nomor_transaksi,
        'tanggal': instance.tanggal.strftime('%d/%m/%Y') if instance.tanggal else '-',
        'kategori': str(instance.kategori) if instance.kategori else '-',
        'jumlah': format_angka(instance.jumlah),
        'deskripsi': instance.deskripsi or '-',
        'status': instance.get_status_display() if hasattr(instance, 'get_status_display') else instance.status,
        'dibuat_oleh': instance.dibuat_oleh.get_full_name() or instance.dibuat_oleh.username if instance.dibuat_oleh else '-',
        'metode_pembayaran': str(instance.metode_pembayaran) if instance.metode_pembayaran else '-',
    }

    if _is_kirim_pdf_aktif():
        from .pdf_generator import generate_biaya_pdf
        kirim_dokumen_async('biaya', instance.nomor_transaksi, instance, generate_biaya_pdf, data)
    else:
        kirim_notifikasi_async('biaya', instance.nomor_transaksi, data)


def kirim_notifikasi_penggajian(instance):
    """
    Kirim notifikasi Telegram untuk Slip Gaji karyawan.
    Jika kirim_pdf aktif: kirim PDF dengan caption template (1 pesan).
    Jika tidak: kirim teks notifikasi saja.
    """
    instance.refresh_from_db()

    # Hitung total tunjangan dan potongan untuk template pesan
    total_tunjangan = (
        instance.tunjangan_jabatan +
        instance.tunjangan_makan +
        instance.tunjangan_transport +
        instance.tunjangan_lainnya
    )

    total_potongan = (
        instance.potongan_bpjs_kesehatan +
        instance.potongan_bpjs_ketenagakerjaan +
        instance.potongan_pph21 +
        instance.potongan_lainnya
    )

    nomor_ref = f"GAJI/{instance.karyawan.nik}/{instance.periode_bulan}/{instance.periode_tahun}"

    data = {
        'nama_karyawan': instance.karyawan.nama,
        'nik': instance.karyawan.nik,
        'jabatan': instance.karyawan.jabatan.nama if instance.karyawan.jabatan else '-',
        'departemen': instance.karyawan.departemen.nama if instance.karyawan.departemen else '-',
        'periode': instance.periode,
        'gaji_pokok': format_angka(instance.gaji_pokok),
        'tunjangan': format_angka(total_tunjangan),
        'potongan': format_angka(total_potongan),
        'gaji_bersih': format_angka(instance.gaji_bersih),
        'status': instance.get_status_display() if hasattr(instance, 'get_status_display') else instance.status,
    }

    if _is_kirim_pdf_aktif():
        from .pdf_generator import generate_penggajian_pdf
        kirim_dokumen_async('penggajian', nomor_ref, instance, generate_penggajian_pdf, data)
    else:
        kirim_notifikasi_async('penggajian', nomor_ref, data)


def kirim_notifikasi_order_service(instance):
    """
    Kirim notifikasi Telegram untuk Order Service Center.
    Dipanggil dari service_center/views.py saat:
    - Order baru diterima (OrderServiceCreateView)
    - Status order berubah (update_status)
    Jika kirim_pdf aktif: kirim PDF dengan caption template (1 pesan).
    Jika tidak: kirim teks notifikasi saja.
    """
    instance.refresh_from_db()

    # Detail items layanan
    items = instance.items.all()
    detail_items = ""
    for i, item in enumerate(items, 1):
        detail_items += f"  {i}. {item.nama_layanan} = Rp {format_angka(item.biaya)}\n"

    if not detail_items:
        detail_items = "  (Belum ada item layanan)"

    # Detail sparepart
    detail_sparepart = ""
    total_sparepart = 0
    for sp in instance.penggunaan_sparepart.select_related('produk').all():
        detail_sparepart += f"  \u2022 {sp.produk.nama} x{sp.jumlah} = Rp {format_angka(sp.subtotal)}\n"
        total_sparepart += float(sp.subtotal)

    if not detail_sparepart:
        detail_sparepart = "  (Tidak ada sparepart)"

    data = {
        'nomor_service': instance.nomor_service,
        'kode_tracking': instance.kode_unik,
        'tanggal_masuk': instance.tanggal_masuk.strftime('%d/%m/%Y %H:%M') if instance.tanggal_masuk else '-',
        'pelanggan': str(instance.pelanggan) if instance.pelanggan else '-',
        'telepon': instance.pelanggan.telepon if instance.pelanggan else '-',
        'perangkat': f'{instance.merek} {instance.model_tipe or ""}',
        'jenis_perangkat': str(instance.jenis_perangkat) if instance.jenis_perangkat else '-',
        'keluhan': instance.keluhan or '-',
        'status': instance.get_status_display() if hasattr(instance, 'get_status_display') else instance.status,
        'prioritas': instance.get_prioritas_display() if hasattr(instance, 'get_prioritas_display') else instance.prioritas,
        'teknisi': instance.teknisi.get_full_name() or instance.teknisi.username if instance.teknisi else '-',
        'detail_items': detail_items.strip(),
        'detail_sparepart': detail_sparepart.strip(),
        'total_sparepart': format_angka(total_sparepart),
        'biaya_akhir': format_angka(instance.biaya_akhir or 0),
        'dp_bayar': format_angka(instance.dp_bayar or 0),
        'sisa_bayar': format_angka(instance.sisa_bayar or 0),
        'status_bayar': instance.get_status_bayar_display() if hasattr(instance, 'get_status_bayar_display') else instance.status_bayar,
        'diterima_oleh': instance.diterima_oleh.get_full_name() or instance.diterima_oleh.username if instance.diterima_oleh else '-',
    }

    if _is_kirim_pdf_aktif():
        # Kirim PDF nota service dengan caption template
        try:
            from .pdf_generator import generate_service_pdf
            kirim_dokumen_async('order_service', instance.nomor_service, instance, generate_service_pdf, data)
        except (ImportError, AttributeError):
            # Fallback: kirim teks saja jika PDF generator belum tersedia
            kirim_notifikasi_async('order_service', instance.nomor_service, data)
    else:
        kirim_notifikasi_async('order_service', instance.nomor_service, data)
