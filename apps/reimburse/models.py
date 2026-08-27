from django.db import models
from django.contrib.auth.models import User
from apps.core.validators import validate_expense_proof


class ReimburseRequest(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Diajukan'),
        ('approved', 'Disetujui'),
        ('rejected', 'Ditolak'),
        ('paid', 'Dibayar'),
        ('completed', 'Selesai'),
        ('cancelled', 'Dibatalkan'),
    ]

    nomor = models.CharField(max_length=50, unique=True, verbose_name="Nomor Reimburse")
    pemohon = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='reimburse_diajukan', verbose_name="Pemohon"
    )
    tanggal = models.DateField(verbose_name="Tanggal Pengajuan")
    keterangan = models.TextField(verbose_name="Keterangan")
    total = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Total Reimburse")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft', verbose_name="Status")

    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reimburse_disetujui', verbose_name="Disetujui Oleh"
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="Tanggal Disetujui")
    rejection_reason = models.TextField(blank=True, default='', verbose_name="Alasan Penolakan")

    metode_pembayaran = models.ForeignKey(
        'pos.MetodePembayaran', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='transaksi_reimburse', verbose_name="Metode Pembayaran"
    )
    tanggal_bayar = models.DateField(null=True, blank=True, verbose_name="Tanggal Bayar")

    cancelled_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reimburse_dibatalkan', verbose_name="Dibatalkan Oleh"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name="Tanggal Dibatalkan")

    dibuat_oleh = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='reimburse_dibuat'
    )
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Reimburse"
        verbose_name_plural = "Reimburse"
        ordering = ['-tanggal', '-dibuat_pada']
        indexes = [
            models.Index(fields=['tanggal', 'status'], name='rmb_tgl_status_idx'),
            models.Index(fields=['pemohon', 'status'], name='rmb_pemohon_status_idx'),
            models.Index(fields=['status'], name='rmb_status_idx'),
        ]

    VALID_TRANSITIONS = {
        'draft': ['submitted'],
        'submitted': ['approved', 'rejected'],
        'approved': ['paid', 'cancelled'],
        'rejected': ['draft'],
        'paid': ['completed', 'cancelled'],
        'completed': [],
        'cancelled': [],
    }

    def transition_status(self, new_status, user=None):
        from django.core.exceptions import ValidationError
        valid_targets = self.VALID_TRANSITIONS.get(self.status, [])
        if new_status not in valid_targets:
            raise ValidationError(
                f"Transisi status tidak valid: '{self.get_status_display()}' → '{new_status}'. "
                f"Yang diizinkan: {valid_targets}"
            )
        self.status = new_status
        return self

    def __str__(self):
        return f"{self.nomor} - {self.pemohon} - Rp {self.total:,.0f}"

    def save(self, *args, **kwargs):
        from django.db import transaction
        with transaction.atomic():
            if not self.nomor:
                self.nomor = self.generate_nomor()
            super().save(*args, **kwargs)

    def generate_nomor(self):
        from django.utils import timezone
        today = timezone.now()
        prefix = f"RMB/{today.year}/{today.month:02d}"
        last = ReimburseRequest.objects.select_for_update().filter(
            nomor__startswith=prefix
        ).order_by('-nomor').first()
        if last:
            try:
                new_number = int(last.nomor.split('/')[-1]) + 1
            except (ValueError, IndexError):
                new_number = ReimburseRequest.objects.filter(
                    nomor__startswith=prefix
                ).count() + 1
        else:
            new_number = 1
        nomor = f"{prefix}/{new_number:04d}"
        while ReimburseRequest.objects.filter(nomor=nomor).exists():
            new_number += 1
            nomor = f"{prefix}/{new_number:04d}"
        return nomor


class ReimburseItem(models.Model):
    request = models.ForeignKey(
        ReimburseRequest, on_delete=models.CASCADE, related_name='items', verbose_name="Pengajuan"
    )
    kategori = models.ForeignKey(
        'biaya.KategoriBiaya', on_delete=models.PROTECT, related_name='items_reimburse',
        verbose_name="Kategori"
    )
    deskripsi = models.CharField(max_length=255, verbose_name="Deskripsi")
    nominal = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Nominal")
    bukti = models.FileField(
        upload_to='reimburse/bukti/', blank=True, null=True,
        verbose_name="Bukti (Foto/PDF)", validators=[validate_expense_proof]
    )

    class Meta:
        verbose_name = "Item Reimburse"
        verbose_name_plural = "Item Reimburse"
        ordering = ['id']

    def __str__(self):
        return f"{self.deskripsi} - Rp {self.nominal:,.0f}"
