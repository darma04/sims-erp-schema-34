import logging
from decimal import Decimal
from django.db import transaction as db_transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def ensure_reimburse_accounting(reimburse, user=None):
    from apps.akuntansi.models import JurnalEntry
    from apps.akuntansi.services import create_jurnal
    from apps.kas_bank.services import create_operational_mutation, resolve_kas_bank_mapping

    if not reimburse.metode_pembayaran:
        logger.error(f"[JURNAL GAGAL] Reimburse {reimburse.nomor}: metode_pembayaran tidak diset")
        return None

    try:
        kas_bank_account, _, akun_kas_kode = resolve_kas_bank_mapping(reimburse.metode_pembayaran)
    except Exception as e:
        logger.error(f"[JURNAL GAGAL] Reimburse {reimburse.nomor}: resolve_kas_bank_mapping gagal - {e}")
        return None

    lines_data = []
    total = Decimal(str(reimburse.total))

    for item in reimburse.items.all():
        akun_kode = item.kategori.akun_beban.kode if item.kategori.akun_beban else '6-9000'
        nominal = Decimal(str(item.nominal))
        found = False
        for line in lines_data:
            if line['akun_kode'] == akun_kode:
                line['debit'] += nominal
                found = True
                break
        if not found:
            lines_data.append({
                'akun_kode': akun_kode,
                'debit': nominal,
                'kredit': Decimal('0'),
                'keterangan': f'Reimburse - {item.deskripsi}'
            })

    lines_data.append({
        'akun_kode': akun_kas_kode,
        'debit': Decimal('0'),
        'kredit': total,
        'keterangan': f'Pembayaran reimburse {reimburse.nomor} ke {reimburse.pemohon}'
    })

    with db_transaction.atomic():
        if JurnalEntry.objects.select_for_update().filter(
            sumber='reimburse', sumber_id=reimburse.pk
        ).exists():
            return None

        jurnal = create_jurnal(
            tanggal=reimburse.tanggal_bayar or timezone.now().date(),
            deskripsi=f'Reimburse {reimburse.nomor} - {reimburse.keterangan[:100]}',
            lines_data=lines_data,
            sumber='reimburse',
            sumber_id=reimburse.pk,
            sumber_ref=reimburse.nomor,
            cabang=getattr(reimburse, 'cabang', None),
            user=user,
            auto_post=True,
        )
        create_operational_mutation(
            akun_kas_bank=kas_bank_account,
            tipe='keluar',
            tanggal=reimburse.tanggal_bayar or timezone.now().date(),
            jumlah=total,
            deskripsi=f'Reimburse {reimburse.nomor} - {reimburse.pemohon}',
            cabang=getattr(reimburse, 'cabang', None),
            metode_pembayaran=reimburse.metode_pembayaran,
            sumber_app='reimburse',
            sumber_model='Reimburse',
            sumber_id=reimburse.pk,
            sumber_ref=reimburse.nomor,
            jurnal_entry=jurnal,
            user=user,
        )

    return jurnal


def cancel_reimburse_accounting(reimburse, user=None):
    from apps.akuntansi.models import JurnalEntry
    from apps.akuntansi.services import create_reversal_jurnal

    jurnal = JurnalEntry.objects.filter(sumber='reimburse', sumber_id=reimburse.pk).first()
    if not jurnal:
        return None

    reversal = create_reversal_jurnal(jurnal, user=user)
    return reversal
