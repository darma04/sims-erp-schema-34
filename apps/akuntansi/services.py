"""
==========================================================================
 AKUNTANSI SERVICES - Service Layer untuk Jurnal Otomatis & Kalkulasi
==========================================================================
 Layer ini berisi fungsi-fungsi helper yang:
 1. Membuat jurnal otomatis dari modul operasional
 2. Menghitung saldo akun
 3. Menyediakan data untuk laporan keuangan

 Fungsi-fungsi ini dipanggil oleh signals di masing-masing modul:
 - penjualan/signals.py → create_jurnal (SO confirmed)
 - pembelian/signals.py → create_jurnal (PO confirmed)
 - pos/signals.py       → create_jurnal (POS completed)
 - biaya/signals.py     → ensure_biaya_accounting (biaya approved)
 - hr/signals.py        → create_jurnal (penggajian dibayar)
 - kas_bank/signals.py  → post_manual/transfer (mutasi posted)
 - pajak/signals.py     → create_jurnal (PPN setor/restitusi)
 - aset/signals.py      → create_jurnal (pembelian/depresiasi aset)
 - hutang: auto-jurnal di PembayaranHutang.save()
 - piutang: auto-jurnal di PembayaranPiutang.save()
==========================================================================
"""

from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Q
from apps.akuntansi.models import Akun, JurnalEntry, JurnalLine, PeriodeAkuntansi


def get_akun_by_kode(kode):
    """Ambil akun berdasarkan kode. Return None jika tidak ditemukan."""
    try:
        return Akun.objects.get(kode=kode, is_active=True)
    except Akun.DoesNotExist:
        return None


def get_periode_for_tanggal(tanggal):
    """Return periode akuntansi yang mencakup tanggal transaksi."""
    if hasattr(tanggal, 'date'):
        tanggal = tanggal.date()
    return (
        PeriodeAkuntansi.objects
        .filter(tanggal_mulai__lte=tanggal, tanggal_akhir__gte=tanggal)
        .order_by('-tanggal_mulai')
        .first()
    )


def validate_periode_open(tanggal, periode=None, allow_closed_period=False):
    """Validasi agar jurnal biasa tidak masuk ke periode yang sudah tutup."""
    if hasattr(tanggal, 'date'):
        tanggal = tanggal.date()
    periode = periode or get_periode_for_tanggal(tanggal)
    if periode and not (periode.tanggal_mulai <= tanggal <= periode.tanggal_akhir):
        raise ValueError(f"Tanggal jurnal berada di luar rentang periode {periode.nama}.")
    if periode and periode.is_tutup and not allow_closed_period:
        raise ValueError(
            f"Periode {periode.nama} sudah ditutup. Gunakan jurnal pembalik atau periode baru."
        )
    return periode


def create_jurnal(tanggal, deskripsi, lines_data, sumber='manual',
                  sumber_id=None, sumber_ref='', cabang=None, user=None,
                  auto_post=True, periode=None, allow_closed_period=False):
    """
    Buat jurnal entry dengan validasi double-entry.

    Parameters:
    - tanggal: date
    - deskripsi: str
    - lines_data: list of dict [{'akun_kode': '1-1000', 'debit': 100000, 'kredit': 0, 'keterangan': ''}]
    - sumber: str (manual, pos, so, po, biaya, payroll, dll)
    - sumber_id: int (PK dari objek sumber)
    - sumber_ref: str (nomor transaksi sumber)
    - cabang: Gudang instance
    - user: User instance
    - auto_post: bool (langsung posting atau draft)

    Returns: JurnalEntry instance

    Raises: ValueError jika jurnal tidak balance
    """
    periode = validate_periode_open(tanggal, periode=periode, allow_closed_period=allow_closed_period)

    if not lines_data:
        raise ValueError("Jurnal harus memiliki minimal satu baris detail.")

    # Validasi balance sebelum create
    total_debit = sum(Decimal(str(l.get('debit', 0))) for l in lines_data)
    total_kredit = sum(Decimal(str(l.get('kredit', 0))) for l in lines_data)

    if total_debit <= 0 and total_kredit <= 0:
        raise ValueError("Nominal jurnal harus lebih besar dari 0.")

    if total_debit != total_kredit:
        raise ValueError(
            f"Jurnal tidak balance! Debit: {total_debit:,.0f} ≠ Kredit: {total_kredit:,.0f}"
        )

    with transaction.atomic():
        # Create header
        jurnal = JurnalEntry.objects.create(
            tanggal=tanggal,
            deskripsi=deskripsi,
            sumber=sumber,
            sumber_id=sumber_id,
            sumber_ref=sumber_ref,
            cabang=cabang,
            periode=periode,
            created_by=user,
            is_posted=auto_post,
        )

        # Create lines
        for line_data in lines_data:
            akun_kode = line_data.get('akun_kode', '')
            akun = line_data.get('akun') or get_akun_by_kode(akun_kode)

            if not akun:
                raise ValueError(f"Akun dengan kode '{akun_kode}' tidak ditemukan.")

            JurnalLine.objects.create(
                jurnal=jurnal,
                akun=akun,
                debit=Decimal(str(line_data.get('debit', 0))),
                kredit=Decimal(str(line_data.get('kredit', 0))),
                keterangan=line_data.get('keterangan', ''),
            )

    return jurnal


def create_jurnal_pembalik(jurnal_asal, user=None):
    """
    Buat jurnal pembalik dari jurnal asal (swap debit ↔ kredit).

    Parameters:
    - jurnal_asal: JurnalEntry yang akan dibalik
    - user: User yang membuat pembalik

    Returns: JurnalEntry (jurnal pembalik)
    """
    lines_data = []
    for line in jurnal_asal.lines.all():
        lines_data.append({
            'akun': line.akun,
            'debit': line.kredit,      # Swap: kredit → debit
            'kredit': line.debit,      # Swap: debit → kredit
            'keterangan': f"Pembalik: {line.keterangan}",
        })

    from django.utils import timezone

    tanggal_pembalik = jurnal_asal.tanggal
    if jurnal_asal.periode_id and jurnal_asal.periode.is_tutup:
        tanggal_pembalik = timezone.now().date()

    pembalik = create_jurnal(
        tanggal=tanggal_pembalik,
        deskripsi=f"[PEMBALIK] {jurnal_asal.deskripsi}",
        lines_data=lines_data,
        sumber='pembalik',
        sumber_id=jurnal_asal.pk,
        sumber_ref=jurnal_asal.nomor,
        cabang=jurnal_asal.cabang,
        user=user,
        auto_post=True,
    )

    # Set reference balik
    pembalik.jurnal_asal = jurnal_asal
    pembalik.save()

    return pembalik


def create_reversal_jurnal(jurnal_entry, tanggal=None, alasan='', user=None):
    """
    Buat jurnal reversal (pembatalan) dari jurnal asal.

    Berbeda dengan create_jurnal_pembalik():
    - create_jurnal_pembalik() → untuk koreksi manual (sumber='pembalik')
    - create_reversal_jurnal() → untuk pembatalan otomatis (sumber tetap sama,
      sumber_ref + '_reversal', mark is_reversed=True)

    Parameters:
    - jurnal_entry: JurnalEntry yang akan di-reverse
    - tanggal: date untuk reversal (default: jurnal_entry.tanggal atau hari ini jika periode tutup)
    - alasan: str alasan pembatalan
    - user: User yang melakukan reversal

    Returns: JurnalEntry (jurnal reversal)

    Raises: ValueError jika jurnal sudah di-reverse sebelumnya
    """
    if jurnal_entry.is_reversed:
        raise ValueError("Jurnal ini sudah di-reverse sebelumnya.")

    with transaction.atomic():
        # Ambil semua lines dari jurnal asal
        lines = jurnal_entry.lines.all()

        # Build lines_data dengan debit↔kredit di-swap
        lines_data = []
        for line in lines:
            lines_data.append({
                'akun': line.akun,
                'debit': line.kredit,      # Swap: kredit → debit
                'kredit': line.debit,      # Swap: debit → kredit
                'keterangan': f"Reversal: {line.keterangan}",
            })

        # Tentukan tanggal reversal
        from django.utils import timezone
        if tanggal:
            tanggal_reversal = tanggal
        elif jurnal_entry.periode_id and jurnal_entry.periode.is_tutup:
            # Periode sudah tutup → gunakan tanggal hari ini
            tanggal_reversal = timezone.now().date()
        else:
            tanggal_reversal = jurnal_entry.tanggal

        # Build deskripsi reversal
        deskripsi = f"[REVERSAL] {jurnal_entry.deskripsi}"
        if alasan:
            deskripsi += f" | Alasan: {alasan}"

        # Build sumber_ref
        if jurnal_entry.sumber_ref:
            sumber_ref = f"{jurnal_entry.sumber_ref}_reversal"
        else:
            sumber_ref = f"REV-{jurnal_entry.nomor}"

        # Buat jurnal reversal via create_jurnal()
        reversal = create_jurnal(
            tanggal=tanggal_reversal,
            deskripsi=deskripsi,
            lines_data=lines_data,
            sumber=jurnal_entry.sumber,
            sumber_id=jurnal_entry.sumber_id,
            sumber_ref=sumber_ref,
            cabang=jurnal_entry.cabang,
            user=user,
            auto_post=True,
        )

        # Set referensi ke jurnal asal
        reversal.jurnal_asal = jurnal_entry
        reversal.save()

        # Mark jurnal asal sebagai sudah di-reverse
        jurnal_entry.is_reversed = True
        jurnal_entry.save()

    return reversal


def get_saldo_akun(akun, tanggal_akhir=None, tanggal_mulai=None, cabang=None):
    """
    Hitung saldo akun berdasarkan semua jurnal yang sudah diposting.

    Akun Debit (Aset, Beban, HPP): Saldo = SUM(Debit) - SUM(Kredit)
    Akun Kredit (Kewajiban, Modal, Pendapatan): Saldo = SUM(Kredit) - SUM(Debit)

    Returns: Decimal (saldo)
    """
    filters = Q(jurnal__is_posted=True, akun=akun)

    if tanggal_mulai:
        filters &= Q(jurnal__tanggal__gte=tanggal_mulai)
    if tanggal_akhir:
        filters &= Q(jurnal__tanggal__lte=tanggal_akhir)
    if cabang:
        filters &= Q(jurnal__cabang=cabang)

    aggregated = JurnalLine.objects.filter(filters).aggregate(
        total_debit=Sum('debit'),
        total_kredit=Sum('kredit'),
    )

    total_debit = aggregated['total_debit'] or Decimal('0')
    total_kredit = aggregated['total_kredit'] or Decimal('0')

    if akun.saldo_normal == 'debit':
        return total_debit - total_kredit
    else:
        return total_kredit - total_debit


def _get_saldo_bulk(tanggal_akhir=None, tanggal_mulai=None, cabang=None):
    """
    Hitung saldo SEMUA akun dalam 1 query aggregate (menghilangkan N+1 problem).

    Returns: dict {akun_id: {'total_debit': Decimal, 'total_kredit': Decimal}}
    """
    filters = Q(jurnal__is_posted=True)
    if tanggal_mulai:
        filters &= Q(jurnal__tanggal__gte=tanggal_mulai)
    if tanggal_akhir:
        filters &= Q(jurnal__tanggal__lte=tanggal_akhir)
    if cabang:
        filters &= Q(jurnal__cabang=cabang)

    aggregated = JurnalLine.objects.filter(filters).values('akun_id').annotate(
        total_debit=Sum('debit'),
        total_kredit=Sum('kredit'),
    )

    return {
        item['akun_id']: {
            'total_debit': item['total_debit'] or Decimal('0'),
            'total_kredit': item['total_kredit'] or Decimal('0'),
        }
        for item in aggregated
    }


def _calc_saldo_from_bulk(akun, bulk_data):
    """Hitung saldo satu akun dari hasil bulk query."""
    data = bulk_data.get(akun.id, {'total_debit': Decimal('0'), 'total_kredit': Decimal('0')})
    if akun.saldo_normal == 'debit':
        return data['total_debit'] - data['total_kredit']
    else:
        return data['total_kredit'] - data['total_debit']


def _display_saldo_laporan(akun, saldo):
    """Saldo untuk laporan: akun kontra mengurangi kelompok utamanya."""
    if akun.sub_tipe in {'contra_aset', 'contra_pendapatan'}:
        return -saldo
    return saldo


def get_all_saldo_akun(tanggal_akhir=None, tanggal_mulai=None, cabang=None, tipe=None):
    """
    Hitung saldo semua akun aktif (optimized — 1 query aggregate).

    Returns: list of dict [{'akun': Akun, 'saldo': Decimal}]
    """
    filters = Q(is_active=True)
    if tipe:
        filters &= Q(tipe=tipe)

    akun_list = Akun.objects.filter(filters).order_by('kode')
    bulk_data = _get_saldo_bulk(tanggal_akhir, tanggal_mulai, cabang)

    result = []
    for akun in akun_list:
        saldo = _calc_saldo_from_bulk(akun, bulk_data)
        result.append({'akun': akun, 'saldo': saldo})
    return result


def get_neraca(tanggal, cabang=None):
    """
    Hitung data Neraca (Balance Sheet) pada tanggal tertentu.
    Optimized: Menggunakan 1 bulk query untuk semua saldo akun.

    Returns: dict {
        'aset_lancar': [...], 'aset_tetap': [...],
        'kewajiban': [...], 'modal': [...],
        'total_aktiva': Decimal, 'total_pasiva': Decimal,
        'is_balanced': bool
    }
    """
    # Satu kali query untuk semua saldo akun
    bulk_data = _get_saldo_bulk(tanggal_akhir=tanggal, cabang=cabang)

    def get_group(tipe, sub_tipe_filter=None):
        filters = Q(is_active=True, tipe=tipe)
        if sub_tipe_filter:
            filters &= Q(sub_tipe__in=sub_tipe_filter)
        items = []
        total = Decimal('0')
        for akun in Akun.objects.filter(filters).order_by('kode'):
            raw_saldo = _calc_saldo_from_bulk(akun, bulk_data)
            saldo = _display_saldo_laporan(akun, raw_saldo)
            items.append({'akun': akun, 'saldo': saldo, 'raw_saldo': raw_saldo})
            total += saldo
        return items, total

    aset_lancar, total_aset_lancar = get_group('aset', ['aset_lancar'])
    aset_tetap, total_aset_tetap = get_group('aset', ['aset_tetap', 'contra_aset'])
    kewajiban, total_kewajiban = get_group('kewajiban')
    modal, total_modal = get_group('modal')

    # Laba bersih tahun berjalan (dari pendapatan - hpp - beban)
    _, total_pendapatan = get_group('pendapatan')
    _, total_hpp = get_group('hpp')
    _, total_beban = get_group('beban')
    laba_bersih = total_pendapatan - total_hpp - total_beban

    total_aktiva = total_aset_lancar + total_aset_tetap
    total_pasiva = total_kewajiban + total_modal + laba_bersih

    return {
        'aset_lancar': aset_lancar, 'total_aset_lancar': total_aset_lancar,
        'aset_tetap': aset_tetap, 'total_aset_tetap': total_aset_tetap,
        'kewajiban': kewajiban, 'total_kewajiban': total_kewajiban,
        'modal': modal, 'total_modal': total_modal,
        'laba_bersih': laba_bersih,
        'total_aktiva': total_aktiva,
        'total_pasiva': total_pasiva,
        'is_balanced': total_aktiva == total_pasiva,
    }


def get_laba_rugi(tanggal_mulai, tanggal_akhir, cabang=None):
    """
    Hitung data Laba Rugi (Income Statement) untuk periode tertentu.
    Optimized: Menggunakan 1 bulk query untuk semua saldo akun.

    Returns: dict dengan komponen laporan laba rugi
    """
    # Satu kali query untuk semua saldo akun pada periode
    bulk_data = _get_saldo_bulk(tanggal_akhir=tanggal_akhir, tanggal_mulai=tanggal_mulai, cabang=cabang)

    def get_group(tipe):
        items = []
        total = Decimal('0')
        for akun in Akun.objects.filter(is_active=True, tipe=tipe).order_by('kode'):
            raw_saldo = _calc_saldo_from_bulk(akun, bulk_data)
            saldo = _display_saldo_laporan(akun, raw_saldo) if tipe == 'pendapatan' else raw_saldo
            if raw_saldo != 0:
                items.append({'akun': akun, 'saldo': saldo, 'raw_saldo': raw_saldo})
                total += saldo
        return items, total

    pendapatan_items, total_pendapatan = get_group('pendapatan')
    hpp_items, total_hpp = get_group('hpp')
    beban_items, total_beban = get_group('beban')
    total_pendapatan_bruto = sum(
        item['raw_saldo'] for item in pendapatan_items
        if item['akun'].sub_tipe != 'contra_pendapatan'
    )
    total_kontra_pendapatan = sum(
        item['raw_saldo'] for item in pendapatan_items
        if item['akun'].sub_tipe == 'contra_pendapatan'
    )

    laba_kotor = total_pendapatan - total_hpp
    laba_bersih = laba_kotor - total_beban

    return {
        'pendapatan': pendapatan_items, 'total_pendapatan': total_pendapatan,
        'total_pendapatan_bruto': total_pendapatan_bruto,
        'total_kontra_pendapatan': total_kontra_pendapatan,
        'hpp': hpp_items, 'total_hpp': total_hpp,
        'beban': beban_items, 'total_beban': total_beban,
        'laba_kotor': laba_kotor,
        'laba_bersih': laba_bersih,
    }


def get_buku_besar(akun, tanggal_mulai=None, tanggal_akhir=None, cabang=None):
    """
    Hitung data Buku Besar (General Ledger) untuk akun tertentu.

    Returns: list of dict dengan mutasi dan saldo berjalan
    """
    filters = Q(jurnal__is_posted=True, akun=akun)
    if tanggal_mulai:
        filters &= Q(jurnal__tanggal__gte=tanggal_mulai)
    if tanggal_akhir:
        filters &= Q(jurnal__tanggal__lte=tanggal_akhir)
    if cabang:
        filters &= Q(jurnal__cabang=cabang)

    lines = JurnalLine.objects.filter(filters).select_related(
        'jurnal', 'jurnal__cabang'
    ).order_by('jurnal__tanggal', 'jurnal__nomor')

    # Hitung saldo awal (sebelum tanggal_mulai)
    saldo_awal = Decimal('0')
    if tanggal_mulai:
        awal_filters = Q(jurnal__is_posted=True, akun=akun, jurnal__tanggal__lt=tanggal_mulai)
        if cabang:
            awal_filters &= Q(jurnal__cabang=cabang)
        awal_agg = JurnalLine.objects.filter(awal_filters).aggregate(
            total_d=Sum('debit'), total_k=Sum('kredit')
        )
        d = awal_agg['total_d'] or Decimal('0')
        k = awal_agg['total_k'] or Decimal('0')
        saldo_awal = (d - k) if akun.saldo_normal == 'debit' else (k - d)

    # Build mutasi dengan saldo berjalan
    saldo_berjalan = saldo_awal
    result = []
    for line in lines:
        if akun.saldo_normal == 'debit':
            saldo_berjalan += line.debit - line.kredit
        else:
            saldo_berjalan += line.kredit - line.debit

        result.append({
            'tanggal': line.jurnal.tanggal,
            'nomor_jurnal': line.jurnal.nomor,
            'jurnal_id': line.jurnal.pk,
            'deskripsi': line.jurnal.deskripsi,
            'keterangan': line.keterangan,
            'debit': line.debit,
            'kredit': line.kredit,
            'saldo': saldo_berjalan,
            'cabang': line.jurnal.cabang,
        })

    return {
        'akun': akun,
        'saldo_awal': saldo_awal,
        'mutasi': result,
        'saldo_akhir': saldo_berjalan,
        'total_debit': sum(r['debit'] for r in result),
        'total_kredit': sum(r['kredit'] for r in result),
    }


# ==================== DATA SEED CoA DEFAULT ====================

DEFAULT_COA = [
    # ASET (1-xxxx)
    {'kode': '1-1000', 'nama': 'Kas', 'tipe': 'aset', 'sub_tipe': 'aset_lancar', 'saldo_normal': 'debit'},
    {'kode': '1-1100', 'nama': 'Bank BCA', 'tipe': 'aset', 'sub_tipe': 'aset_lancar', 'saldo_normal': 'debit'},
    {'kode': '1-1200', 'nama': 'Bank Mandiri', 'tipe': 'aset', 'sub_tipe': 'aset_lancar', 'saldo_normal': 'debit'},
    {'kode': '1-1500', 'nama': 'PPN Masukan (Dibayar Dimuka)', 'tipe': 'aset', 'sub_tipe': 'aset_lancar', 'saldo_normal': 'debit'},
    {'kode': '1-2000', 'nama': 'Piutang Usaha', 'tipe': 'aset', 'sub_tipe': 'aset_lancar', 'saldo_normal': 'debit'},
    {'kode': '1-2100', 'nama': 'Penyisihan Piutang', 'tipe': 'aset', 'sub_tipe': 'contra_aset', 'saldo_normal': 'kredit'},
    {'kode': '1-3000', 'nama': 'Persediaan Barang', 'tipe': 'aset', 'sub_tipe': 'aset_lancar', 'saldo_normal': 'debit'},
    {'kode': '1-4000', 'nama': 'Peralatan & Inventaris', 'tipe': 'aset', 'sub_tipe': 'aset_tetap', 'saldo_normal': 'debit'},
    {'kode': '1-4100', 'nama': 'Akumulasi Penyusutan', 'tipe': 'aset', 'sub_tipe': 'contra_aset', 'saldo_normal': 'kredit'},
    {'kode': '1-4200', 'nama': 'Kendaraan', 'tipe': 'aset', 'sub_tipe': 'aset_tetap', 'saldo_normal': 'debit'},
    {'kode': '1-4300', 'nama': 'Bangunan', 'tipe': 'aset', 'sub_tipe': 'aset_tetap', 'saldo_normal': 'debit'},
    # KEWAJIBAN (2-xxxx)
    {'kode': '2-1000', 'nama': 'Hutang Usaha (ke Supplier)', 'tipe': 'kewajiban', 'sub_tipe': 'kewajiban_lancar', 'saldo_normal': 'kredit'},
    {'kode': '2-2000', 'nama': 'Hutang PPN (Keluaran)', 'tipe': 'kewajiban', 'sub_tipe': 'kewajiban_lancar', 'saldo_normal': 'kredit'},
    {'kode': '2-3000', 'nama': 'Hutang Gaji', 'tipe': 'kewajiban', 'sub_tipe': 'kewajiban_lancar', 'saldo_normal': 'kredit'},
    {'kode': '2-3100', 'nama': 'Hutang PPh 21', 'tipe': 'kewajiban', 'sub_tipe': 'kewajiban_lancar', 'saldo_normal': 'kredit'},
    {'kode': '2-3200', 'nama': 'Hutang BPJS', 'tipe': 'kewajiban', 'sub_tipe': 'kewajiban_lancar', 'saldo_normal': 'kredit'},
    {'kode': '2-4000', 'nama': 'Hutang Bank / Leasing', 'tipe': 'kewajiban', 'sub_tipe': 'kewajiban_panjang', 'saldo_normal': 'kredit'},
    # MODAL (3-xxxx)
    {'kode': '3-1000', 'nama': 'Modal Pemilik', 'tipe': 'modal', 'sub_tipe': 'modal_pemilik', 'saldo_normal': 'kredit'},
    {'kode': '3-2000', 'nama': 'Laba Ditahan', 'tipe': 'modal', 'sub_tipe': 'laba_ditahan', 'saldo_normal': 'kredit'},
    {'kode': '3-3000', 'nama': 'Prive (Penarikan Pemilik)', 'tipe': 'modal', 'sub_tipe': 'prive', 'saldo_normal': 'debit'},
    {'kode': '3-9000', 'nama': 'Ikhtisar Laba/Rugi', 'tipe': 'modal', 'sub_tipe': 'ikhtisar', 'saldo_normal': 'kredit'},
    # PENDAPATAN (4-xxxx)
    {'kode': '4-1000', 'nama': 'Pendapatan Penjualan', 'tipe': 'pendapatan', 'sub_tipe': 'pendapatan_utama', 'saldo_normal': 'kredit'},
    {'kode': '4-1001', 'nama': 'Retur Penjualan', 'tipe': 'pendapatan', 'sub_tipe': 'contra_pendapatan', 'saldo_normal': 'debit'},
    {'kode': '4-1002', 'nama': 'Diskon Penjualan', 'tipe': 'pendapatan', 'sub_tipe': 'contra_pendapatan', 'saldo_normal': 'debit'},
    {'kode': '4-2000', 'nama': 'Pendapatan Jasa Service', 'tipe': 'pendapatan', 'sub_tipe': 'pendapatan_utama', 'saldo_normal': 'kredit'},
    {'kode': '4-3000', 'nama': 'Pendapatan Lainnya', 'tipe': 'pendapatan', 'sub_tipe': 'pendapatan_lain', 'saldo_normal': 'kredit'},
    # HPP (5-xxxx)
    {'kode': '5-1000', 'nama': 'HPP - Barang Dagang', 'tipe': 'hpp', 'sub_tipe': 'hpp_utama', 'saldo_normal': 'debit'},
    # BEBAN (6-xxxx)
    {'kode': '6-1000', 'nama': 'Beban Gaji & Tunjangan', 'tipe': 'beban', 'sub_tipe': 'beban_operasional', 'saldo_normal': 'debit'},
    {'kode': '6-2000', 'nama': 'Beban Listrik & Air', 'tipe': 'beban', 'sub_tipe': 'beban_operasional', 'saldo_normal': 'debit'},
    {'kode': '6-3000', 'nama': 'Beban Sewa', 'tipe': 'beban', 'sub_tipe': 'beban_operasional', 'saldo_normal': 'debit'},
    {'kode': '6-4000', 'nama': 'Beban Penyusutan', 'tipe': 'beban', 'sub_tipe': 'beban_operasional', 'saldo_normal': 'debit'},
    {'kode': '6-5000', 'nama': 'Beban Kerusakan/Kehilangan', 'tipe': 'beban', 'sub_tipe': 'beban_operasional', 'saldo_normal': 'debit'},
    {'kode': '6-6000', 'nama': 'Beban Piutang Tak Tertagih', 'tipe': 'beban', 'sub_tipe': 'beban_operasional', 'saldo_normal': 'debit'},
    {'kode': '6-7000', 'nama': 'Beban Transport & Pengiriman', 'tipe': 'beban', 'sub_tipe': 'beban_operasional', 'saldo_normal': 'debit'},
    {'kode': '6-8000', 'nama': 'Beban PPh Badan', 'tipe': 'beban', 'sub_tipe': 'beban_operasional', 'saldo_normal': 'debit'},
    {'kode': '6-9000', 'nama': 'Beban Operasional Lainnya', 'tipe': 'beban', 'sub_tipe': 'beban_operasional', 'saldo_normal': 'debit'},
]


def seed_default_coa():
    """
    Seed Chart of Accounts default dari daftar standar PSAK.
    Hanya menambahkan akun yang belum ada (cek by kode).

    Returns: tuple (created_count, skipped_count)
    """
    created = 0
    skipped = 0

    for data in DEFAULT_COA:
        akun, was_created = Akun.objects.get_or_create(
            kode=data['kode'],
            defaults={
                'nama': data['nama'],
                'tipe': data['tipe'],
                'sub_tipe': data['sub_tipe'],
                'saldo_normal': data['saldo_normal'],
                'is_system': True,
                'is_active': True,
            }
        )
        if was_created:
            created += 1
        else:
            skipped += 1

    return created, skipped
