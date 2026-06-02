"""
==========================================================================
 HUTANG MODELS - Accounts Payable (AP)
==========================================================================
 Model:
 1. Hutang           → Header hutang (dari PO kredit)
 2. PembayaranHutang → Detail pelunasan (partial/full)
==========================================================================
"""

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from decimal import Decimal


class Hutang(models.Model):
    """
    Model HUTANG USAHA — kewajiban bayar ke supplier.

    Sumber hutang:
    - Purchase Order dengan status kredit/tempo
    - Input manual
    """

    STATUS_CHOICES = [
        ('belum_bayar', 'Belum Bayar'),
        ('sebagian', 'Bayar Sebagian'),
        ('lunas', 'Lunas'),
        ('macet', 'Macet'),
    ]

    SUMBER_CHOICES = [
        ('po', 'Purchase Order'),
        ('manual', 'Input Manual'),
    ]

    # Nomor hutang unik — auto-generate: AP/2026/05/0001
    nomor = models.CharField(max_length=50, unique=True, verbose_name="No. Hutang", editable=False)

    # Relasi ke Supplier (dari modul pembelian)
    supplier = models.ForeignKey(
        'pembelian.Supplier', on_delete=models.PROTECT,
        related_name='hutang_set', verbose_name="Supplier"
    )

    # Sumber hutang
    sumber = models.CharField(max_length=10, choices=SUMBER_CHOICES, default='manual', verbose_name="Sumber")

    # Referensi ke PO (opsional)
    purchase_order = models.ForeignKey(
        'pembelian.PurchaseOrder', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='hutang_set', verbose_name="Purchase Order"
    )
    sumber_ref = models.CharField(max_length=100, blank=True, default='', verbose_name="No. Referensi Sumber")

    # Nilai hutang
    jumlah_total = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Jumlah Total")
    jumlah_dibayar = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Jumlah Dibayar")

    @property
    def sisa(self):
        return self.jumlah_total - self.jumlah_dibayar

    # Tanggal & jatuh tempo
    tanggal = models.DateField(verbose_name="Tanggal Hutang", default=timezone.now)
    jatuh_tempo = models.DateField(verbose_name="Jatuh Tempo", null=True, blank=True)

    # Status
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='belum_bayar', verbose_name="Status")

    # Cabang
    cabang = models.ForeignKey(
        'produk.Gudang', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='hutang_set', verbose_name="Cabang"
    )

    keterangan = models.TextField(blank=True, default='', verbose_name="Keterangan")

    # Relasi ke Jurnal (untuk tracking jurnal pembayaran)
    jurnal_pembayaran = models.ForeignKey(
        'akuntansi.JurnalEntry',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='pembayaran_hutang',
        verbose_name="Jurnal Pembayaran",
        help_text="Jurnal otomatis saat hutang dibayar"
    )

    # Tracking
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Dibuat Oleh")
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Hutang"
        verbose_name_plural = "Hutang"
        ordering = ['-tanggal', '-dibuat_pada']
        indexes = [
            models.Index(fields=['tanggal', 'status'], name='ap_tgl_status_idx'),
            models.Index(fields=['jatuh_tempo', 'status'], name='ap_due_status_idx'),
            models.Index(fields=['supplier', 'status'], name='ap_sup_status_idx'),
            models.Index(fields=['cabang', 'status'], name='ap_cabang_status_idx'),
            models.Index(fields=['sumber', 'sumber_ref'], name='ap_source_ref_idx'),
        ]

    def __str__(self):
        return f"{self.nomor} - {self.supplier.nama}"

    def save(self, *args, **kwargs):
        if not self.nomor:
            self.nomor = self.generate_nomor()
        if self.jumlah_dibayar >= self.jumlah_total and self.jumlah_total > 0:
            self.status = 'lunas'
        elif self.jumlah_dibayar > 0:
            self.status = 'sebagian'
        elif self.status in ('lunas', 'sebagian'):
            self.status = 'belum_bayar'
        super().save(*args, **kwargs)

    def generate_nomor(self):
        today = timezone.now()
        prefix = f"AP/{today.year}/{today.month:02d}"
        with transaction.atomic():
            last = Hutang.objects.select_for_update().filter(
                nomor__startswith=prefix
            ).order_by('-nomor').first()
            if last:
                try:
                    last_num = int(last.nomor.split('/')[-1])
                    new_num = last_num + 1
                except (ValueError, IndexError):
                    new_num = Hutang.objects.filter(nomor__startswith=prefix).count() + 1
            else:
                new_num = 1
            nomor = f"{prefix}/{new_num:04d}"
            while Hutang.objects.filter(nomor=nomor).exists():
                new_num += 1
                nomor = f"{prefix}/{new_num:04d}"
        return nomor

    @property
    def is_overdue(self):
        if self.jatuh_tempo and self.status not in ('lunas',):
            return timezone.now().date() > self.jatuh_tempo
        return False

    @property
    def hari_overdue(self):
        if self.is_overdue:
            return (timezone.now().date() - self.jatuh_tempo).days
        return 0

    @property
    def aging_bucket(self):
        if self.status == 'lunas':
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


class PembayaranHutang(models.Model):
    """
    Model PEMBAYARAN HUTANG — setiap kali kita bayar ke supplier.

    Setiap pembayaran:
    1. Mengurangi sisa hutang
    2. Membuat jurnal otomatis: D:Hutang Usaha K:Kas/Bank
    """

    hutang = models.ForeignKey(
        Hutang, on_delete=models.CASCADE,
        related_name='pembayaran_set', verbose_name="Hutang"
    )
    tanggal = models.DateField(verbose_name="Tanggal Bayar", default=timezone.now)
    jumlah = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Jumlah Bayar")

    metode_pembayaran = models.ForeignKey(
        'pos.MetodePembayaran', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Metode Pembayaran"
    )

    keterangan = models.TextField(blank=True, default='', verbose_name="Keterangan")

    jurnal = models.ForeignKey(
        'akuntansi.JurnalEntry', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="Jurnal Entry"
    )

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name="Dicatat Oleh")
    dibuat_pada = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pembayaran Hutang"
        verbose_name_plural = "Pembayaran Hutang"
        ordering = ['-tanggal', '-dibuat_pada']
        indexes = [
            models.Index(fields=['tanggal'], name='ap_pay_tanggal_idx'),
            models.Index(fields=['hutang', 'tanggal'], name='ap_pay_hutang_tgl_idx'),
            models.Index(fields=['metode_pembayaran', 'tanggal'], name='ap_pay_metode_tgl_idx'),
        ]

    def __str__(self):
        return f"Bayar {self.hutang.nomor} - Rp {self.jumlah:,.0f}"

    def save(self, *args, **kwargs):
        if self.jumlah <= 0:
            raise ValidationError("Jumlah pembayaran harus lebih dari 0")

        with transaction.atomic():
            hutang = Hutang.objects.select_for_update().get(pk=self.hutang_id)
            pembayaran_lain = hutang.pembayaran_set.exclude(pk=self.pk).aggregate(
                total=models.Sum('jumlah')
            )['total'] or Decimal('0')

            if pembayaran_lain + self.jumlah > hutang.jumlah_total:
                raise ValidationError("Jumlah pembayaran melebihi sisa hutang")

            super().save(*args, **kwargs)

            total_bayar = hutang.pembayaran_set.aggregate(
                total=models.Sum('jumlah')
            )['total'] or Decimal('0')
            hutang.jumlah_dibayar = total_bayar
            hutang.save()

            if not self.jurnal_id:
                try:
                    from apps.akuntansi.services import create_jurnal
                    from apps.kas_bank.services import create_operational_mutation, resolve_kas_bank_mapping

                    kas_bank_account, _, akun_kas_kode = resolve_kas_bank_mapping(self.metode_pembayaran)
                    jurnal = create_jurnal(
                        tanggal=self.tanggal,
                        deskripsi=f"Pembayaran Hutang {hutang.nomor} - {hutang.supplier.nama}",
                        lines_data=[
                            {'akun_kode': '2-1000', 'debit': self.jumlah, 'kredit': 0,
                             'keterangan': f'Pelunasan hutang {hutang.nomor}'},
                            {'akun_kode': akun_kas_kode, 'debit': 0, 'kredit': self.jumlah,
                             'keterangan': f'Pembayaran ke {hutang.supplier.nama}'},
                        ],
                        sumber='hutang',
                        sumber_id=hutang.pk,
                        sumber_ref=hutang.nomor,
                        cabang=hutang.cabang,
                        user=self.created_by,
                        auto_post=True,
                    )
                    create_operational_mutation(
                        akun_kas_bank=kas_bank_account,
                        tipe='keluar',
                        tanggal=self.tanggal,
                        jumlah=self.jumlah,
                        deskripsi=f"Pembayaran Hutang {hutang.nomor}",
                        akun_lawan=None,
                        cabang=hutang.cabang,
                        metode_pembayaran=self.metode_pembayaran,
                        sumber_app='hutang',
                        sumber_model='PembayaranHutang',
                        sumber_id=self.pk,
                        sumber_ref=hutang.nomor,
                        jurnal_entry=jurnal,
                        user=self.created_by,
                    )
                    PembayaranHutang.objects.filter(pk=self.pk).update(jurnal=jurnal)
                    self.jurnal = jurnal
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"[HUTANG] Auto-jurnal gagal untuk pembayaran #{self.pk}: {e}")
                    raise ValueError(f"Auto-jurnal pembayaran hutang gagal: {e}")
            return

        # Update total dibayar pada hutang induk
        # ── Auto-Jurnal: D:Hutang Usaha  K:Kas/Bank ──
        # Hanya buat jurnal saat record baru dan belum punya jurnal
    def delete(self, *args, **kwargs):
        hutang = self.hutang
        with transaction.atomic():
            hutang = Hutang.objects.select_for_update().get(pk=hutang.pk)
            result = super().delete(*args, **kwargs)
            total_bayar = hutang.pembayaran_set.aggregate(
                total=models.Sum('jumlah')
            )['total'] or Decimal('0')
            hutang.jumlah_dibayar = total_bayar
            hutang.save()
            return result


from django.db.models.signals import pre_delete
from django.dispatch import receiver as signal_receiver


@signal_receiver(pre_delete, sender=PembayaranHutang)
def reverse_jurnal_on_pembayaran_hutang_delete(sender, instance, **kwargs):
    """
    Reverse jurnal pembayaran hutang saat record dihapus.
    Memastikan tidak ada jurnal gantung tanpa dokumen sumber.
    """
    if instance.jurnal_id and instance.jurnal and not instance.jurnal.is_reversed:
        try:
            from apps.akuntansi.services import create_reversal_jurnal
            create_reversal_jurnal(
                instance.jurnal,
                alasan=f'Penghapusan pembayaran hutang #{instance.pk}',
                user=instance.created_by
            )
        except Exception as exc:
            raise ValueError(f"Reverse jurnal pembayaran hutang gagal: {exc}")

    # Cancel mutasi kas/bank terkait
    from apps.kas_bank.models import KasBankTransaction
    KasBankTransaction.objects.filter(
        sumber_app='hutang',
        sumber_model='PembayaranHutang',
        sumber_id=instance.pk,
        status='posted'
    ).update(status='cancelled')
