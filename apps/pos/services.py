"""
==========================================================================
 POS SERVICES - Service Layer untuk POS Kasbon (Unpaid) Accounting
==========================================================================
 Fungsi ini menangani integrasi akuntansi untuk POS kasbon (status='unpaid'):
 1. Buat JurnalEntry Penjualan: D:Piutang(1-2000) K:Pendapatan(4-1000)+PPN(2-2000)
 2. Buat JurnalEntry HPP: D:HPP(5-1000) K:Persediaan(1-3000)
 3. Buat record Piutang di modul piutang
 4. TIDAK buat KasBankTransaction (karena belum ada uang masuk)

 Dipanggil dari: pos/signals.py saat POSTransaction.status = 'unpaid'
 Pola: mengikuti ensure_biaya_accounting() di biaya/services.py
==========================================================================
"""

from decimal import Decimal
from django.db import transaction

from apps.akuntansi.models import JurnalEntry
from apps.akuntansi.services import create_jurnal


@transaction.atomic
def ensure_pos_kasbon_accounting(pos_transaction, user=None):
    """
    Pastikan POS kasbon (unpaid) memiliki jurnal dan piutang.
    Idempotent: jika jurnal sudah ada, tidak membuat duplikat.

    Parameters:
        pos_transaction: POSTransaction instance dengan status='unpaid'
        user: User yang melakukan operasi (default: pos_transaction.kasir)

    Returns:
        JurnalEntry (jurnal penjualan) atau None jika skip

    Raises:
        ValueError jika total <= 0
    """
    if pos_transaction.status != 'unpaid':
        return None

    total = pos_transaction.total_harga or Decimal('0')
    subtotal = pos_transaction.subtotal or Decimal('0')
    pajak = pos_transaction.pajak or Decimal('0')
    diskon = pos_transaction.diskon or Decimal('0')

    if total <= 0:
        return None

    _resolve_kasbon_customer(pos_transaction)

    # Idempotent check — jangan buat duplikat jurnal
    if JurnalEntry.objects.filter(sumber='pos', sumber_id=pos_transaction.pk).exists():
        # Jurnal sudah ada, pastikan piutang juga ada
        _ensure_piutang_for_kasbon(pos_transaction, user)
        from apps.pos.signals import ensure_pos_faktur_pajak
        ensure_pos_faktur_pajak(pos_transaction, subtotal, diskon, pajak)
        return None

    # Hitung HPP
    hpp_total = sum(
        (item.hpp_subtotal or (
            (item.produk.harga_beli or Decimal('0')) *
            (item.jumlah_konversi or item.jumlah or Decimal('0'))
        ))
        for item in pos_transaction.items.select_related('produk')
    )

    user = user or pos_transaction.kasir
    tanggal = pos_transaction.tanggal.date() if hasattr(pos_transaction.tanggal, 'date') else pos_transaction.tanggal

    with transaction.atomic():
        # ── Jurnal Penjualan: D:Piutang K:Pendapatan+PPN ──
        lines_data = [
            {
                'akun_kode': '1-2000',  # Piutang Usaha
                'debit': total,
                'kredit': Decimal('0'),
                'keterangan': f'Piutang dari POS kasbon {pos_transaction.nomor_transaksi}'
            },
            {
                'akun_kode': '4-1000',  # Pendapatan Penjualan
                'debit': Decimal('0'),
                'kredit': subtotal,
                'keterangan': f'Pendapatan penjualan POS kasbon {pos_transaction.nomor_transaksi}'
            }
        ]

        # Diskon sebagai contra-pendapatan
        if diskon > 0:
            lines_data.append({
                'akun_kode': '4-1002',  # Diskon Penjualan
                'debit': diskon,
                'kredit': Decimal('0'),
                'keterangan': f'Diskon penjualan POS kasbon {pos_transaction.nomor_transaksi}'
            })

        # PPN Keluaran
        if pajak > 0:
            lines_data.append({
                'akun_kode': '2-2000',  # PPN Keluaran
                'debit': Decimal('0'),
                'kredit': pajak,
                'keterangan': f'PPN Keluaran POS kasbon {pos_transaction.nomor_transaksi}'
            })

        jurnal_penjualan = create_jurnal(
            tanggal=tanggal,
            deskripsi=f'Penjualan POS Kasbon - {pos_transaction.nomor_transaksi}',
            lines_data=lines_data,
            sumber='pos',
            sumber_id=pos_transaction.pk,
            sumber_ref=pos_transaction.nomor_transaksi,
            cabang=pos_transaction.gudang,
            user=user,
            auto_post=True,
        )

        # ── Jurnal HPP: D:HPP K:Persediaan ──
        if hpp_total > 0:
            create_jurnal(
                tanggal=tanggal,
                deskripsi=f'HPP POS Kasbon - {pos_transaction.nomor_transaksi}',
                lines_data=[
                    {
                        'akun_kode': '5-1000',  # HPP
                        'debit': hpp_total,
                        'kredit': Decimal('0'),
                        'keterangan': f'HPP penjualan POS kasbon {pos_transaction.nomor_transaksi}'
                    },
                    {
                        'akun_kode': '1-3000',  # Persediaan
                        'debit': Decimal('0'),
                        'kredit': hpp_total,
                        'keterangan': f'Pengurangan persediaan POS kasbon {pos_transaction.nomor_transaksi}'
                    },
                ],
                sumber='pos',
                sumber_id=pos_transaction.pk,
                sumber_ref=f'{pos_transaction.nomor_transaksi}_hpp',
                cabang=pos_transaction.gudang,
                user=user,
                auto_post=True,
            )

        # ── Buat record Piutang ──
        _ensure_piutang_for_kasbon(pos_transaction, user)

        # ── Buat mutasi kas/bank untuk DP (jika ada uang muka) ──
        from apps.pos.signals import ensure_pos_faktur_pajak
        ensure_pos_faktur_pajak(pos_transaction, subtotal, diskon, pajak)

        jumlah_bayar = pos_transaction.jumlah_bayar or Decimal('0')
        if jumlah_bayar > 0:
            from apps.kas_bank.services import create_operational_mutation, resolve_kas_bank_mapping
            kas_bank_account, _, akun_kas_kode = resolve_kas_bank_mapping(pos_transaction.metode_pembayaran)
            if kas_bank_account:
                create_operational_mutation(
                    akun_kas_bank=kas_bank_account,
                    tipe='masuk',
                    tanggal=pos_transaction.tanggal,
                    jumlah=jumlah_bayar,
                    deskripsi=f'DP/Uang Muka POS Kasbon {pos_transaction.nomor_transaksi}',
                    akun_lawan=None,
                    cabang=pos_transaction.gudang,
                    metode_pembayaran=pos_transaction.metode_pembayaran,
                    sumber_app='pos',
                    sumber_model='POSTransaction',
                    sumber_id=pos_transaction.pk,
                    sumber_ref=pos_transaction.nomor_transaksi,
                    jurnal_entry=jurnal_penjualan,
                    user=user,
                )

    return jurnal_penjualan


def _resolve_kasbon_customer(pos_transaction):
    """
    Pastikan POS kasbon punya Customer terdaftar agar piutang valid.

    POS tunai boleh walk-in tanpa customer, tetapi POS kasbon menciptakan
    piutang sehingga wajib punya FK Customer. Untuk data lama atau input kasir
    yang hanya mengisi nama_customer, buat customer operasional deterministik
    dan snapshot-kan ke transaksi tanpa memicu signal ulang.
    """
    if pos_transaction.customer_id:
        return pos_transaction.customer

    from apps.penjualan.models import Customer

    nama = (pos_transaction.nama_customer or "").strip()
    if not nama:
        nama = f"Customer POS {pos_transaction.nomor_transaksi}"

    kode = f"POS-{pos_transaction.pk:06d}"
    customer, _ = Customer.objects.get_or_create(
        kode=kode,
        defaults={
            "nama": nama[:200],
            "aktif": True,
        },
    )

    updated = pos_transaction.__class__.objects.filter(
        pk=pos_transaction.pk,
        customer__isnull=True,
    ).update(customer=customer)
    if updated:
        pos_transaction.customer = customer
        pos_transaction.customer_id = customer.pk

    return customer


def _ensure_piutang_for_kasbon(pos_transaction, user=None):
    """
    Pastikan POS kasbon memiliki record Piutang. Idempotent.
    Piutang = total_harga - jumlah_bayar (jika ada DP/uang muka).
    """
    from apps.piutang.models import Piutang
    from datetime import timedelta

    total = pos_transaction.total_harga or Decimal('0')
    jumlah_bayar = pos_transaction.jumlah_bayar or Decimal('0')
    
    # Piutang = sisa yang belum dibayar
    sisa_piutang = total - jumlah_bayar
    if sisa_piutang <= 0:
        return None  # Sudah lunas, tidak perlu piutang

    tanggal_pos = pos_transaction.tanggal.date() if hasattr(pos_transaction.tanggal, 'date') else pos_transaction.tanggal
    jatuh_tempo = pos_transaction.jatuh_tempo or (tanggal_pos + timedelta(days=30))

    # Cek customer — gunakan customer terdaftar atau buat referensi
    customer = _resolve_kasbon_customer(pos_transaction)
    if not customer:
        # POS kasbon tanpa customer terdaftar — tidak bisa buat piutang
        # (piutang butuh FK ke Customer)
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            f"[POS] Kasbon {pos_transaction.nomor_transaksi} tidak memiliki customer terdaftar. "
            f"Piutang tidak dapat dibuat. Silakan assign customer terlebih dahulu."
        )
        return None

    # Idempotent: cek apakah piutang sudah ada
    piutang, created = Piutang.objects.get_or_create(
        sumber='pos',
        pos_transaction=pos_transaction,
        defaults={
            'customer': customer,
            'sumber_ref': pos_transaction.nomor_transaksi,
            'tanggal': tanggal_pos,
            'jatuh_tempo': jatuh_tempo,
            'jumlah_total': sisa_piutang,
            'jumlah_dibayar': Decimal('0'),
            'status': 'belum_bayar',
            'cabang': pos_transaction.gudang,
            'keterangan': f'Piutang dari POS kasbon {pos_transaction.nomor_transaksi}',
            'created_by': user or pos_transaction.kasir,
        }
    )
    return piutang


@transaction.atomic
def handle_pos_kasbon_payment(pos_transaction, user=None):
    """
    Dipanggil saat POS kasbon dilunasi via PembayaranPiutang.
    Update status POSTransaction: unpaid → paid.
    TIDAK membuat ulang jurnal Penjualan/HPP (sudah ada dari ensure_pos_kasbon_accounting).

    Parameters:
        pos_transaction: POSTransaction instance
        user: User yang melakukan pelunasan
    """
    if pos_transaction.status != 'unpaid':
        return

    # Update status ke paid — jurnal pelunasan sudah dihandle oleh PembayaranPiutang.save()
    pos_transaction.status = 'paid'
    pos_transaction.save(update_fields=['status'])


@transaction.atomic
def transition_pos_status(pos_transaction, new_status, user=None):
    """
    Atomic: validate transition + create/reverse journal + stock + piutang/mutasi.

    Cancellation (NEW):
    - paid/unpaid → cancelled: reversal journal + restore stock + cancel piutang/mutasi

    Parameters:
        pos_transaction: POSTransaction instance
        new_status: target status string
        user: User performing the action

    Returns:
        POSTransaction instance (saved)
    """
    from apps.pos.models import POSTransaction
    from apps.akuntansi.services import create_reversal_jurnal
    import logging

    logger = logging.getLogger(__name__)

    with transaction.atomic():
        locked = POSTransaction.objects.select_for_update().get(pk=pos_transaction.pk)
        old_status = locked.status

        # Validate transition menggunakan state machine
        from django.core.exceptions import ValidationError
        VALID_TRANSITIONS = {
            'draft': ['paid', 'unpaid', 'cancelled'],
            'unpaid': ['paid', 'cancelled'],
            'paid': ['cancelled'],
            'cancelled': [],
        }
        valid_targets = VALID_TRANSITIONS.get(old_status, [])
        if new_status not in valid_targets:
            raise ValidationError(
                f"Transisi status POS tidak valid: '{old_status}' → '{new_status}'. "
                f"Transisi yang diizinkan: {valid_targets}"
            )

        locked.status = new_status

        if new_status == 'cancelled':
            _cancel_pos(locked, old_status, user)

        locked.save()

    return locked


def _cancel_pos(pos, old_status, user):
    """Handle POS cancellation: reversal journal + restore stock + cancel piutang/mutasi."""
    from apps.produk.models import Stok
    from apps.kas_bank.models import KasBankTransaction
    from apps.akuntansi.services import create_reversal_jurnal
    import logging

    logger = logging.getLogger(__name__)

    # 1. Reverse all journals for this POS
    jurnals = JurnalEntry.objects.filter(sumber='pos', sumber_id=pos.pk, is_reversed=False)
    for jurnal in jurnals:
        try:
            create_reversal_jurnal(jurnal, alasan=f'Pembatalan POS {pos.nomor_transaksi}', user=user)
        except ValueError:
            pass

    # 2. Restore stock
    if old_status in ('paid', 'unpaid'):
        for item in pos.items.select_related('produk'):
            qty_restore = item.jumlah_konversi if item.jumlah_konversi else item.jumlah
            stok, _ = Stok.objects.select_for_update().get_or_create(
                produk=item.produk, gudang=pos.gudang, defaults={'jumlah': Decimal('0')}
            )
            stok.jumlah += qty_restore
            stok.save()

            # Update cabang produk ke gudang dengan stok terbanyak
            produk = item.produk
            stok_terbanyak = Stok.objects.filter(
                produk=produk, jumlah__gt=0
            ).order_by('-jumlah').first()
            if stok_terbanyak and produk.cabang != stok_terbanyak.gudang:
                produk.cabang = stok_terbanyak.gudang
                produk.save(update_fields=['cabang'])

    # 3. Cancel KasBankTransaction
    KasBankTransaction.objects.filter(
        sumber_app='pos', sumber_model='POSTransaction', sumber_id=pos.pk, status='posted'
    ).update(status='cancelled')

    # 4. Cancel Piutang (jika kasbon)
    try:
        from apps.piutang.models import Piutang
        Piutang.objects.filter(
            sumber='pos', pos_transaction=pos
        ).exclude(status__in=['lunas', 'dihapuskan']).update(status='dihapuskan')
    except Exception as e:
        logger.warning(f"[POS] Gagal cancel piutang untuk {pos.nomor_transaksi}: {e}")

    # 5. Log ke activity_log
    try:
        from apps.activity_log.models import UserActivity
        UserActivity.objects.create(
            user=user,
            action='cancel',
            model_name='POSTransaction',
            object_id=str(pos.pk),
            object_repr=f'Pembatalan POS {pos.nomor_transaksi}',
            description=(
                f'POS {pos.nomor_transaksi} dibatalkan dari status {old_status}. '
                f'Jurnal di-reverse, stok dikembalikan, piutang/mutasi dibatalkan.'
            ),
            source_type='pos',
            source_id=str(pos.pk),
            source_repr=pos.nomor_transaksi,
        )
    except Exception as e:
        logger.warning(f"[POS] Gagal log activity untuk pembatalan {pos.nomor_transaksi}: {e}")
