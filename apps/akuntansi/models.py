"""
==========================================================================
 AKUNTANSI MODELS - Model Inti Akuntansi ERP
==========================================================================
 File ini berisi 4 model untuk modul Akuntansi:

 1. Akun (Chart of Accounts) → Master daftar akun keuangan
 2. PeriodeAkuntansi → Periode buka/tutup buku
 3. JurnalEntry → Header jurnal (nomor, tanggal, sumber, status)
 4. JurnalLine → Detail jurnal (akun, debit, kredit)

 STANDAR:
 - Double-entry bookkeeping (PSAK/IFRS)
 - Validasi SUM(Debit) == SUM(Kredit) pada setiap jurnal
 - Jurnal posted tidak boleh dihapus (koreksi via jurnal pembalik)
 - Dimensi cabang pada JurnalEntry untuk laporan per cabang

 Koneksi:
 - apps/produk/models.py → Gudang sebagai dimensi cabang
 - apps/pos/ → Trigger jurnal dari POS
 - apps/penjualan/ → Trigger jurnal dari Sales Order
 - apps/pembelian/ → Trigger jurnal dari Purchase Order
 - apps/biaya/ → Trigger jurnal dari biaya operasional
 - apps/hr/ → Trigger jurnal dari penggajian
 - apps/inventory/ → Trigger jurnal dari adjustment stok
==========================================================================
"""

from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from decimal import Decimal


class Akun(models.Model):
    """
    Model untuk CHART OF ACCOUNTS (CoA) — Master Daftar Akun Keuangan.

    Kode akun mengikuti standar hierarki internasional:
    1-xxxx = Aset (Aktiva)
    2-xxxx = Kewajiban (Liabilitas)
    3-xxxx = Modal (Ekuitas)
    4-xxxx = Pendapatan
    5-xxxx = HPP (Harga Pokok Penjualan)
    6-xxxx = Beban Operasional
    """

    TIPE_CHOICES = [
        ('aset', 'Aset (Aktiva)'),
        ('kewajiban', 'Kewajiban (Liabilitas)'),
        ('modal', 'Modal (Ekuitas)'),
        ('pendapatan', 'Pendapatan'),
        ('hpp', 'Harga Pokok Penjualan'),
        ('beban', 'Beban Operasional'),
    ]

    SUB_TIPE_CHOICES = [
        ('aset_lancar', 'Aset Lancar'),
        ('aset_tetap', 'Aset Tetap'),
        ('contra_aset', 'Contra Aset'),
        ('kewajiban_lancar', 'Kewajiban Lancar'),
        ('kewajiban_panjang', 'Kewajiban Jangka Panjang'),
        ('modal_pemilik', 'Modal Pemilik'),
        ('laba_ditahan', 'Laba Ditahan'),
        ('ikhtisar', 'Ikhtisar Laba/Rugi'),
        ('prive', 'Prive'),
        ('pendapatan_utama', 'Pendapatan Utama'),
        ('contra_pendapatan', 'Contra Pendapatan'),
        ('pendapatan_lain', 'Pendapatan Lainnya'),
        ('hpp_utama', 'HPP Utama'),
        ('beban_operasional', 'Beban Operasional'),
    ]

    SALDO_NORMAL_CHOICES = [
        ('debit', 'Debit'),
        ('kredit', 'Kredit'),
    ]

    # Kode akun unik — format: 1-1000, 2-1000, dll
    kode = models.CharField(
        max_length=20, unique=True, db_index=True,
        verbose_name="Kode Akun",
        help_text="Format: 1-1000 (Aset), 2-1000 (Kewajiban), dll"
    )

    # Nama akun — contoh: 'Kas', 'Piutang Usaha', 'Hutang Usaha'
    nama = models.CharField(max_length=100, verbose_name="Nama Akun")

    # Tipe akun — kategori utama (Aset, Kewajiban, Modal, Pendapatan, HPP, Beban)
    tipe = models.CharField(
        max_length=20, choices=TIPE_CHOICES,
        verbose_name="Tipe Akun"
    )

    # Sub-tipe — detail klasifikasi (Aset Lancar, Aset Tetap, dll)
    sub_tipe = models.CharField(
        max_length=30, choices=SUB_TIPE_CHOICES,
        verbose_name="Sub Tipe", blank=True
    )

    # Parent akun — untuk hierarki (self-referencing FK)
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='children',
        verbose_name="Akun Induk"
    )

    # Saldo normal — Debit untuk Aset/Beban/HPP, Kredit untuk Kewajiban/Modal/Pendapatan
    saldo_normal = models.CharField(
        max_length=10, choices=SALDO_NORMAL_CHOICES,
        verbose_name="Saldo Normal"
    )

    # Deskripsi opsional
    deskripsi = models.TextField(
        blank=True, verbose_name="Deskripsi",
        help_text="Penjelasan tentang akun ini"
    )

    # Flag aktif
    is_active = models.BooleanField(default=True, verbose_name="Aktif")

    # Flag sistem — akun bawaan tidak bisa dihapus
    is_system = models.BooleanField(
        default=False, verbose_name="Akun Sistem",
        help_text="Akun sistem tidak dapat dihapus"
    )

    # Timestamp
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Akun (CoA)"
        verbose_name_plural = "Akun (CoA)"
        ordering = ['kode']
        indexes = [
            models.Index(fields=['tipe', 'is_active'], name='akt_akun_tipe_active_idx'),
            models.Index(fields=['sub_tipe', 'is_active'], name='akt_akun_sub_active_idx'),
        ]

    def __str__(self):
        return f"{self.kode} - {self.nama}"

    @property
    def level(self):
        """Hitung level hierarki berdasarkan parent chain."""
        level = 0
        parent = self.parent
        while parent:
            level += 1
            parent = parent.parent
        return level


class PeriodeAkuntansi(models.Model):
    """
    Model untuk PERIODE AKUNTANSI — Periode buka/tutup buku.

    Contoh: Januari 2026, Februari 2026, dll.
    Jurnal hanya bisa diinput ke periode yang AKTIF dan BELUM DITUTUP.
    """

    # Nama periode — contoh: 'Januari 2026'
    nama = models.CharField(max_length=50, verbose_name="Nama Periode")

    # Tanggal mulai & akhir
    tanggal_mulai = models.DateField(verbose_name="Tanggal Mulai")
    tanggal_akhir = models.DateField(verbose_name="Tanggal Akhir")

    # Flag periode aktif — hanya 1 periode aktif pada satu waktu
    is_aktif = models.BooleanField(default=False, verbose_name="Periode Aktif")

    # Flag tutup buku — setelah ditutup, jurnal tidak bisa diubah
    is_tutup = models.BooleanField(
        default=False, verbose_name="Sudah Ditutup",
        help_text="Periode yang sudah ditutup tidak dapat menerima jurnal baru"
    )

    # Timestamp
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Periode Akuntansi"
        verbose_name_plural = "Periode Akuntansi"
        ordering = ['-tanggal_mulai']
        indexes = [
            models.Index(fields=['is_aktif', 'is_tutup'], name='akt_periode_status_idx'),
        ]

    def __str__(self):
        return self.nama

    def clean(self):
        """Validasi: tanggal_mulai harus sebelum tanggal_akhir."""
        if self.tanggal_mulai and self.tanggal_akhir:
            if self.tanggal_mulai >= self.tanggal_akhir:
                raise ValidationError("Tanggal mulai harus sebelum tanggal akhir.")


class JurnalEntry(models.Model):
    """
    Model untuk JURNAL ENTRY — Header jurnal transaksi.

    Setiap jurnal memiliki:
    - Nomor unik (auto-generate: JU-2026-00001)
    - Tanggal transaksi
    - Sumber (manual, pos, so, po, biaya, payroll, adjustment)
    - Status posting (draft → posted)
    - Dimensi cabang untuk laporan per branch

    ATURAN:
    - Jurnal posted (is_posted=True) TIDAK BOLEH DIHAPUS
    - Koreksi harus memakai Jurnal Pembalik (Reversing Entry)
    - SUM(Debit) HARUS == SUM(Kredit) — Golden Rule
    """

    SUMBER_CHOICES = [
        ('manual', 'Manual'),
        ('pos', 'POS / Kasir'),
        ('so', 'Sales Order'),
        ('po', 'Purchase Order'),
        ('biaya', 'Biaya Operasional'),
        ('payroll', 'Penggajian'),
        ('adjustment', 'Adjustment Stok'),
        ('service', 'Service Center'),
        ('aset', 'Aset Tetap'),
        ('pajak', 'Perpajakan'),
        ('piutang', 'Pembayaran Piutang'),
        ('hutang', 'Pembayaran Hutang'),
        ('kas_bank', 'Kas & Bank / Treasury'),
        ('rekon', 'Rekonsiliasi Kas'),
        ('closing', 'Closing Entry / Tutup Buku'),
        ('pembalik', 'Jurnal Pembalik'),
    ]

    # Nomor jurnal unik — auto-generate: JU-2026-00001
    nomor = models.CharField(
        max_length=30, unique=True, db_index=True,
        verbose_name="Nomor Jurnal"
    )

    # Tanggal transaksi
    tanggal = models.DateField(db_index=True, verbose_name="Tanggal")

    # Deskripsi transaksi
    deskripsi = models.TextField(verbose_name="Deskripsi")

    # Sumber jurnal — dari modul mana jurnal ini berasal
    sumber = models.CharField(
        max_length=20, choices=SUMBER_CHOICES, default='manual',
        verbose_name="Sumber"
    )

    # ID objek sumber — PK dari model sumber (contoh: POS Transaction ID)
    sumber_id = models.IntegerField(
        null=True, blank=True,
        verbose_name="ID Sumber",
        help_text="Primary key dari objek sumber (POS, SO, PO, dll)"
    )

    # Referensi nomor sumber — nomor transaksi dari modul sumber
    sumber_ref = models.CharField(
        max_length=50, blank=True,
        verbose_name="Ref. Sumber",
        help_text="Nomor transaksi sumber (contoh: POS/2026/05/09/0001)"
    )

    # Cabang/gudang — dimensi untuk laporan per cabang
    cabang = models.ForeignKey(
        'produk.Gudang',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Cabang",
        help_text="Cabang yang terkait dengan jurnal ini"
    )

    # Periode akuntansi
    periode = models.ForeignKey(
        PeriodeAkuntansi,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Periode"
    )

    # Status posting
    is_posted = models.BooleanField(
        default=False, verbose_name="Sudah Diposting",
        help_text="Jurnal yang sudah diposting tidak dapat dihapus"
    )

    # Flag apakah jurnal ini sudah memiliki jurnal pembalik/reversal
    is_reversed = models.BooleanField(
        default=False,
        verbose_name="Sudah Di-reverse",
        help_text="True jika jurnal ini sudah memiliki jurnal pembalik/reversal"
    )

    # Jurnal pembalik reference — jika ini adalah jurnal pembalik, tunjuk ke jurnal aslinya
    jurnal_asal = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='jurnal_pembalik',
        verbose_name="Jurnal Asal (jika pembalik)"
    )

    # User yang membuat
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, related_name='jurnal_entries',
        verbose_name="Dibuat Oleh"
    )

    # Timestamp
    dibuat_pada = models.DateTimeField(auto_now_add=True)
    diupdate_pada = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Jurnal Entry"
        verbose_name_plural = "Jurnal Entry"
        ordering = ['-tanggal', '-dibuat_pada']
        indexes = [
            models.Index(fields=['tanggal', 'is_posted'], name='akt_jrn_tgl_post_idx'),
            models.Index(fields=['sumber', 'sumber_id'], name='akt_jrn_src_id_idx'),
            models.Index(fields=['cabang', 'tanggal'], name='akt_jrn_cbg_tgl_idx'),
        ]

    def __str__(self):
        return f"{self.nomor} - {self.deskripsi[:50]}"

    def save(self, *args, **kwargs):
        """Override save untuk auto-generate nomor jurnal."""
        from django.db import transaction
        with transaction.atomic():
            if not self.nomor:
                self.nomor = self.generate_nomor()
            super().save(*args, **kwargs)

    def generate_nomor(self):
        """
        Generate nomor jurnal otomatis.
        Format: JU-{TAHUN}-{NOMOR_URUT_5_DIGIT}
        Contoh: JU-2026-00001
        """
        from datetime import datetime
        today = datetime.now()
        prefix = f"JU-{today.year}"

        last_jurnal = JurnalEntry.objects.select_for_update().filter(
            nomor__startswith=prefix
        ).order_by('-nomor').first()

        if last_jurnal:
            try:
                last_number = int(last_jurnal.nomor.split('-')[-1])
                new_number = last_number + 1
            except (ValueError, IndexError):
                new_number = JurnalEntry.objects.filter(
                    nomor__startswith=prefix
                ).count() + 1
        else:
            new_number = 1

        nomor = f"{prefix}-{new_number:05d}"
        while JurnalEntry.objects.filter(nomor=nomor).exists():
            new_number += 1
            nomor = f"{prefix}-{new_number:05d}"
        return nomor

    @property
    def total_debit(self):
        """Hitung total debit dari semua lines."""
        return sum(line.debit for line in self.lines.all())

    @property
    def total_kredit(self):
        """Hitung total kredit dari semua lines."""
        return sum(line.kredit for line in self.lines.all())

    @property
    def is_balanced(self):
        """Cek apakah jurnal balance (Debit == Kredit)."""
        return self.total_debit == self.total_kredit

    def clean(self):
        """Validasi Golden Rule: SUM(Debit) == SUM(Kredit)."""
        if self.pk:
            total_d = sum(l.debit for l in self.lines.all())
            total_k = sum(l.kredit for l in self.lines.all())
            if total_d != total_k:
                raise ValidationError(
                    f"Jurnal tidak balance! Debit: {total_d:,.0f} ≠ Kredit: {total_k:,.0f}"
                )


class JurnalLine(models.Model):
    """
    Model untuk JURNAL LINE — Detail baris jurnal.

    Setiap baris memiliki:
    - Akun (dari CoA)
    - Debit ATAU Kredit (salah satu harus 0)
    - Keterangan tambahan
    """

    # FK ke JurnalEntry (header)
    jurnal = models.ForeignKey(
        JurnalEntry, on_delete=models.CASCADE,
        related_name='lines',
        verbose_name="Jurnal"
    )

    # FK ke Akun (CoA)
    akun = models.ForeignKey(
        Akun, on_delete=models.PROTECT,
        related_name='jurnal_lines',
        verbose_name="Akun"
    )

    # Nominal debit — 0 jika posisi kredit
    debit = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name="Debit"
    )

    # Nominal kredit — 0 jika posisi debit
    kredit = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        verbose_name="Kredit"
    )

    # Keterangan per baris
    keterangan = models.CharField(
        max_length=200, blank=True,
        verbose_name="Keterangan"
    )

    class Meta:
        verbose_name = "Jurnal Line"
        verbose_name_plural = "Jurnal Lines"
        ordering = ['id']
        indexes = [
            models.Index(fields=['akun', 'jurnal'], name='akt_line_akun_jrn_idx'),
        ]

    def __str__(self):
        if self.debit > 0:
            return f"{self.akun.kode} - D: {self.debit:,.0f}"
        return f"{self.akun.kode} - K: {self.kredit:,.0f}"

    def clean(self):
        """Validasi: debit dan kredit tidak boleh keduanya > 0."""
        if self.debit > 0 and self.kredit > 0:
            raise ValidationError(
                "Debit dan Kredit tidak boleh keduanya berisi nilai. "
                "Pilih salah satu."
            )
        if self.debit < 0 or self.kredit < 0:
            raise ValidationError("Nilai Debit dan Kredit tidak boleh negatif.")
