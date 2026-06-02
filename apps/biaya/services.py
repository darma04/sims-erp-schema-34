from decimal import Decimal

from apps.akuntansi.models import JurnalEntry
from apps.akuntansi.services import create_jurnal, get_akun_by_kode
from apps.biaya.models import TransaksiBiaya
from apps.kas_bank.services import create_operational_mutation, resolve_kas_bank_mapping


def ensure_biaya_accounting(transaksi, user=None):
    """
    Pastikan transaksi biaya approved memiliki jurnal dan mutasi kas/bank.
    Idempotent: jika jurnal/mutasi sudah ada, tidak membuat duplikat.
    """
    if transaksi.status != "approved":
        return None

    jumlah = Decimal(str(transaksi.jumlah or 0))
    if jumlah <= 0:
        raise ValueError("Nominal transaksi biaya harus lebih besar dari 0.")

    kas_bank_account, _, akun_kas_kode = resolve_kas_bank_mapping(transaksi.metode_pembayaran)
    # Gunakan akun_beban dari kategori jika tersedia, fallback ke 6-9000
    akun_biaya = None
    if transaksi.kategori_id and hasattr(transaksi.kategori, 'akun_beban') and transaksi.kategori.akun_beban:
        akun_biaya = transaksi.kategori.akun_beban
    if not akun_biaya:
        akun_biaya = get_akun_by_kode("6-9000")
    if not akun_biaya:
        raise ValueError("Akun 6-9000 Beban Operasional Lainnya belum tersedia di CoA.")

    jurnal = JurnalEntry.objects.filter(
        sumber="biaya",
        sumber_id=transaksi.pk,
        is_reversed=False,
        jurnal_asal__isnull=True,
    ).first()
    if not jurnal:
        jurnal = create_jurnal(
            tanggal=transaksi.tanggal,
            deskripsi=f"Biaya Operasional - {transaksi.nomor_transaksi}",
            lines_data=[
                {
                    "akun": akun_biaya,
                    "debit": jumlah,
                    "kredit": Decimal("0"),
                    "keterangan": transaksi.deskripsi,
                },
                {
                    "akun_kode": akun_kas_kode,
                    "debit": Decimal("0"),
                    "kredit": jumlah,
                    "keterangan": f"Pembayaran biaya {transaksi.nomor_transaksi}",
                },
            ],
            sumber="biaya",
            sumber_id=transaksi.pk,
            sumber_ref=transaksi.nomor_transaksi,
            cabang=transaksi.cabang,
            user=user or transaksi.disetujui_oleh,
            auto_post=True,
        )

    create_operational_mutation(
        akun_kas_bank=kas_bank_account,
        tipe="keluar",
        tanggal=transaksi.tanggal,
        jumlah=jumlah,
        deskripsi=f"Pembayaran Biaya {transaksi.nomor_transaksi}",
        akun_lawan=akun_biaya,
        cabang=transaksi.cabang,
        metode_pembayaran=transaksi.metode_pembayaran,
        sumber_app="biaya",
        sumber_model="TransaksiBiaya",
        sumber_id=transaksi.pk,
        sumber_ref=transaksi.nomor_transaksi,
        jurnal_entry=jurnal,
        user=user or transaksi.disetujui_oleh,
    )
    return jurnal

def transition_biaya_status(transaksi, new_status, user=None):
    """
    Atomic: validate transition + create/reverse journal + mutasi.
    
    Handles:
    - submitted → approved: create jurnal + mutasi via ensure_biaya_accounting()
    - approved → cancelled: create reversal jurnal + cancel mutasi
    - Other transitions: just validate and set status
    
    Parameters:
        transaksi: TransaksiBiaya instance
        new_status: target status string
        user: User performing the action
    
    Returns:
        TransaksiBiaya instance (saved)
    
    Raises:
        ValidationError: if transition is invalid
        ValueError: if accounting operation fails
    """
    from django.db import transaction
    from django.utils import timezone
    from apps.akuntansi.models import JurnalEntry
    from apps.akuntansi.services import create_reversal_jurnal
    from apps.kas_bank.models import KasBankTransaction

    with transaction.atomic():
        # Lock record untuk mencegah race condition
        locked = TransaksiBiaya.objects.select_for_update().get(pk=transaksi.pk)
        
        # Validate transition
        locked.transition_status(new_status, user)
        
        if new_status == 'approved':
            # Set approval info
            locked.disetujui_oleh = user
            locked.save()
            # Create jurnal + mutasi
            ensure_biaya_accounting(locked, user=user)
            
        elif new_status == 'cancelled':
            # Set cancellation info
            locked.cancelled_by = user
            locked.cancelled_at = timezone.now()
            locked.save()
            
            # Reverse jurnal jika ada
            jurnal = JurnalEntry.objects.filter(
                sumber='biaya', sumber_id=locked.pk, is_reversed=False
            ).first()
            if jurnal:
                create_reversal_jurnal(jurnal, alasan='Pembatalan transaksi biaya', user=user)
            
            # Cancel mutasi kas/bank terkait
            KasBankTransaction.objects.filter(
                sumber_app='biaya',
                sumber_model='TransaksiBiaya',
                sumber_id=locked.pk,
                status='posted'
            ).update(status='cancelled')
            
        else:
            # Other transitions (draft→submitted, submitted→rejected, rejected→draft)
            locked.save()
    
    return locked
