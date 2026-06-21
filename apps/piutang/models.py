"""
==========================================================================
 PIUTANG MODELS - Accounts Receivable (AR)
==========================================================================
 Model:
 1. Piutang      → Header piutang (dari SO/POS kredit)
 2. PembayaranPiutang → Detail pelunasan (partial/full)
==========================================================================
"""

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from decimal import Decimal


class Piutang(models.Model):
    """
    Model PIUTANG USAHA — tagihan ke customer yang belum dilunasi.

    Sumber piutang:
    - Sales Order dengan status kredit/tempo
    - POS Transaction dengan kasbon
    - Input manual
    """

    STATUS_CHOICES = [
        ('belum_bayar', 'Belum Bayar'),
        ('sebagian', 'Bayar Sebagian'),
        ('lunas', 'Lunas'),
        ('macet', 'Macet'),
        ('dihapuskan', 'Dihapuskan'),
    ]

    SUMBER_CHOICES = [
        ('so', 'Sales Order'),
        ('pos', 'POS (Kasbon)'),
        ('manual', 'Input Manual'),
    ]

    # Nomor piutang unik — auto-generate: AR/2026/05/0001
    nomor = models.CharField(max_length=50, unique=True, verbose_name="No. Piutang", editable=False)

    # Relasi ke Customer (dari modul penjualan)
    customer = models.ForeignKey(
        'penjualan.Customer', on_delete=models.PROTECT,
        related_name='piutang_set', verbose_name="Customer"
    )

    # Sumber piutang
    sumber = models.CharField(max_length=10, choices=SUMBER_CHOICES, default='manual', verbose_name="Sumber")

    # Referensi ke SO/POS (opsional)
    sales_order = models.ForeignKey(
        'penjualan.SalesOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='piutang_set', verbose_name="Sales Order"
    )
    pos_transaction = models.ForeignKey(
        'pos.POSTransaction', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='piutang_set', verbose_name="POS Transaction"
    )
    sumber_ref = models.CharField(max_length=100, blank=True, default='', verbose_name="No. Referensi Sumber")

    # Nilai piutang
    jumlah_total = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Jumlah Total")
    jumlah_dibayar = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Jumlah Dibayar")

    @property
    def sisa(self):
        """Sisa piutang yang belum dibayar."""
        return self.jumlah_total - self.jumlah_dibayar

    # Tanggal & jatuh tempo
    tanggal = models.DateField(verbose_name="Tanggal Piutang", default=timezone.now)
    jatuh_tempo = models.DateField(verbose_name="Jatuh Tempo", null=True, blank=True)

    # Status
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='belum_bayar', verbose_name="Status")

    # Cabang (dimensi laporan)
    cabang = models.ForeignKey(
        'produk.Gudang', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='piutang_set', verbose_name="Cabang"
    )

    # Keterangan
    keterangan = models.TextField(blank=True, default='', verbose_name="Keterangan")

    # Relasi ke Jurnal (untuk tracking jurnal pembayaran)
    jurnal_pembayaran = models.ForeignKey(
        'akuntansi.JurnalEntry',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='pembayaran_piutang',
        verbose_name="Jurnal Pembayaran",
        help_text="Jurnal otomatis saat piutang dibayar"
    )

    # Tracking
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Dibuat Oleh")
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Piutang"
        verbose_name_plural = "Piutang"
        ordering = ['-tanggal', '-dibuat_pada']
        indexes = [
            models.Index(fields=['tanggal', 'status'], name='ar_tgl_status_idx'),
            models.Index(fields=['jatuh_tempo', 'status'], name='ar_due_status_idx'),
            models.Index(fields=['customer', 'status'], name='ar_cust_status_idx'),
            models.Index(fields=['cabang', 'status'], name='ar_cabang_status_idx'),
            models.Index(fields=['sumber', 'sumber_ref'], name='ar_source_ref_idx'),
        ]

    def __str__(self):
        return f"{self.nomor} - {self.customer.nama}"

    def save(self, *args, **kwargs):
        if not self.nomor:
            self.nomor = self.generate_nomor()
        # Auto-update status
        if self.jumlah_dibayar >= self.jumlah_total and self.jumlah_total > 0:
            self.status = 'lunas'
        elif self.jumlah_dibayar > 0:
            self.status = 'sebagian'
        elif self.status in ('lunas', 'sebagian'):
            self.status = 'belum_bayar'
        super().save(*args, **kwargs)

    def generate_nomor(self):
        today = timezone.now()
        prefix = f"AR/{today.year}/{today.month:02d}"
        with transaction.atomic():
            last = Piutang.objects.select_for_update().filter(
                nomor__startswith=prefix
            ).order_by('-nomor').first()
            if last:
                try:
                    last_num = int(last.nomor.split('/')[-1])
                    new_num = last_num + 1
                except (ValueError, IndexError):
                    new_num = Piutang.objects.filter(nomor__startswith=prefix).count() + 1
            else:
                new_num = 1
            nomor = f"{prefix}/{new_num:04d}"
            while Piutang.objects.filter(nomor=nomor).exists():
                new_num += 1
                nomor = f"{prefix}/{new_num:04d}"
        return nomor

    @property
    def is_overdue(self):
        """Apakah piutang sudah melewati jatuh tempo."""
        if self.jatuh_tempo and self.status not in ('lunas', 'dihapuskan'):
            return timezone.now().date() > self.jatuh_tempo
        return False

    @property
    def hari_overdue(self):
        """Jumlah hari keterlambatan."""
        if self.is_overdue:
            return (timezone.now().date() - self.jatuh_tempo).days
        return 0

    @property
    def aging_bucket(self):
        """Kategori aging: current, 1-30, 31-60, 61-90, >90."""
        if self.status in ('lunas', 'dihapuskan'):
            return 'lunas'
        if not self.jatuh_tempo:
            return 'current'
        days = (timezone.now().date() - self.jatuh_tempo).days
        if days <= 0:
            return 'current'
        elif days <= 30:
            return '1-30'
        elif days <= 60:
            return '31-60'
        elif days <= 90:
            return '61-90'
        else:
            return '>90'


class PembayaranPiutang(models.Model):
    """
    Model PEMBAYARAN PIUTANG — setiap kali customer bayar (partial/full).

    Setiap pembayaran:
    1. Mengurangi sisa piutang
    2. Membuat jurnal otomatis: D:Kas/Bank K:Piutang Usaha
    """

    piutang = models.ForeignKey(
        Piutang, on_delete=models.CASCADE,
        related_name='pembayaran_set', verbose_name="Piutang"
    )
    tanggal = models.DateField(verbose_name="Tanggal Bayar", default=timezone.now)
    jumlah = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Jumlah Bayar")

    # Metode pembayaran (FK ke modul POS)
    metode_pembayaran = models.ForeignKey(
        'pos.MetodePembayaran', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Metode Pembayaran"
    )

    keterangan = models.TextField(blank=True, default='', verbose_name="Keterangan")

    # Referensi ke jurnal otomatis yang dibuat
    jurnal = models.ForeignKey(
        'akuntansi.JurnalEntry', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Jurnal Entry"
    )

    # Tracking
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Dicatat Oleh")
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pembayaran Piutang"
        verbose_name_plural = "Pembayaran Piutang"
        ordering = ['-tanggal', '-dibuat_pada']
        indexes = [
            models.Index(fields=['tanggal'], name='ar_pay_tanggal_idx'),
            models.Index(fields=['piutang', 'tanggal'], name='ar_pay_piutang_tgl_idx'),
            models.Index(fields=['metode_pembayaran', 'tanggal'], name='ar_pay_metode_tgl_idx'),
        ]

    def __str__(self):
        return f"Bayar {self.piutang.nomor} - Rp {self.jumlah:,.0f}"

    def save(self, *args, **kwargs):
        if self.jumlah <= 0:
            raise ValidationError("Jumlah pembayaran harus lebih dari 0")

        with transaction.atomic():
            piutang = Piutang.objects.select_for_update().get(pk=self.piutang_id)
            pembayaran_lain = piutang.pembayaran_set.exclude(pk=self.pk).aggregate(
                total=models.Sum('jumlah')
            )['total'] or Decimal('0')

            if pembayaran_lain + self.jumlah > piutang.jumlah_total:
                raise ValidationError("Jumlah pembayaran melebihi sisa piutang")

            super().save(*args, **kwargs)

            total_bayar = piutang.pembayaran_set.aggregate(
                total=models.Sum('jumlah')
            )['total'] or Decimal('0')
            piutang.jumlah_dibayar = total_bayar
            piutang.save()

            if not self.jurnal_id:
                try:
                    from apps.akuntansi.services import create_jurnal
                    from apps.kas_bank.services import create_operational_mutation, resolve_kas_bank_mapping

                    kas_bank_account, _, akun_kas_kode = resolve_kas_bank_mapping(self.metode_pembayaran)
                    jurnal = create_jurnal(
                        tanggal=self.tanggal,
                        deskripsi=f"Penerimaan Piutang {piutang.nomor} - {piutang.customer.nama}",
                        lines_data=[
                            {'akun_kode': akun_kas_kode, 'debit': self.jumlah, 'kredit': 0,
                             'keterangan': f'Penerimaan dari {piutang.customer.nama}'},
                            {'akun_kode': '1-2000', 'debit': 0, 'kredit': self.jumlah,
                             'keterangan': f'Pelunasan piutang {piutang.nomor}'},
                        ],
                        sumber='piutang',
                        sumber_id=self.pk,
                        sumber_ref=f"{piutang.nomor}/PAY-{self.pk}",
                        cabang=piutang.cabang,
                        user=self.created_by,
                        auto_post=True,
                    )
                    create_operational_mutation(
                        akun_kas_bank=kas_bank_account,
                        tipe='masuk',
                        tanggal=self.tanggal,
                        jumlah=self.jumlah,
                        deskripsi=f"Penerimaan Piutang {piutang.nomor}",
                        akun_lawan=None,
                        cabang=piutang.cabang,
                        metode_pembayaran=self.metode_pembayaran,
                        sumber_app='piutang',
                        sumber_model='PembayaranPiutang',
                        sumber_id=self.pk,
                        sumber_ref=f"{piutang.nomor}/PAY-{self.pk}",
                        jurnal_entry=jurnal,
                        user=self.created_by,
                    )
                    PembayaranPiutang.objects.filter(pk=self.pk).update(jurnal=jurnal)
                    self.jurnal = jurnal
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"[PIUTANG] Auto-jurnal gagal untuk pembayaran #{self.pk}: {e}")
                    raise ValueError(f"Auto-jurnal pembayaran piutang gagal: {e}")

            if piutang.status == 'lunas' and piutang.pos_transaction_id:
                from apps.pos.services import handle_pos_kasbon_payment
                handle_pos_kasbon_payment(piutang.pos_transaction, user=self.created_by)
            return

    def delete(self, *args, **kwargs):
        piutang = self.piutang
        with transaction.atomic():
            piutang = Piutang.objects.select_for_update().get(pk=piutang.pk)
            result = super().delete(*args, **kwargs)
            total_bayar = piutang.pembayaran_set.aggregate(
                total=models.Sum('jumlah')
            )['total'] or Decimal('0')
            piutang.jumlah_dibayar = total_bayar
            piutang.save()
            if piutang.pos_transaction_id and piutang.status != 'lunas':
                pos_trx = piutang.pos_transaction
                if pos_trx.status == 'paid':
                    pos_trx.status = 'unpaid'
                    pos_trx.save(update_fields=['status'])
            return result


from django.db.models.signals import pre_delete
from django.dispatch import receiver as signal_receiver


@signal_receiver(pre_delete, sender=PembayaranPiutang)
def reverse_jurnal_on_pembayaran_piutang_delete(sender, instance, **kwargs):
    """
    Reverse jurnal pembayaran piutang saat record dihapus.
    Memastikan tidak ada jurnal gantung tanpa dokumen sumber.
    """
    if instance.jurnal_id and instance.jurnal and not instance.jurnal.is_reversed:
        try:
            from apps.akuntansi.services import create_reversal_jurnal
            create_reversal_jurnal(
                instance.jurnal,
                alasan=f'Penghapusan pembayaran piutang #{instance.pk}',
                user=instance.created_by
            )
        except Exception as exc:
            raise ValueError(f"Reverse jurnal pembayaran piutang gagal: {exc}")

    # Cancel mutasi kas/bank terkait
    from apps.kas_bank.models import KasBankTransaction
    KasBankTransaction.objects.filter(
        sumber_app='piutang',
        sumber_model='PembayaranPiutang',
        sumber_id=instance.pk,
        status='posted'
    ).update(status='cancelled')
