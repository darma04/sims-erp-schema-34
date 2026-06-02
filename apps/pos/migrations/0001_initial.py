import apps.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('akuntansi', '0001_initial'),
        ('kas_bank', '0001_initial'),
        ('penjualan', '0001_initial'),
        ('produk', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='POSTransactionItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('jumlah', models.DecimalField(decimal_places=2, max_digits=15, verbose_name='Jumlah')),
                ('harga_satuan', models.DecimalField(decimal_places=2, max_digits=15, verbose_name='Harga Satuan')),
                ('diskon', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Diskon')),
                ('subtotal', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Subtotal')),
                ('jumlah_konversi', models.DecimalField(decimal_places=4, default=0, help_text='Jumlah dalam satuan dasar produk, dihitung otomatis', max_digits=15, verbose_name='Jumlah (Satuan Dasar)')),
                ('hpp_satuan', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='HPP Satuan')),
                ('hpp_subtotal', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Subtotal HPP')),
            ],
            options={
                'verbose_name': 'Item Transaksi POS',
                'verbose_name_plural': 'Item Transaksi POS',
            },
        ),
        migrations.CreateModel(
            name='MetodePembayaran',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nama', models.CharField(max_length=50, verbose_name='Nama Metode')),
                ('nama_pemilik', models.CharField(blank=True, max_length=100, null=True, verbose_name='Nama Pemilik')),
                ('kode', models.CharField(max_length=20, unique=True, verbose_name='Kode')),
                ('tipe', models.CharField(choices=[('tunai', 'Tunai'), ('non_tunai', 'Non-Tunai')], default='tunai', help_text='Tunai = pembayaran langsung/cash, Non-Tunai = transfer bank, QRIS, dll', max_length=20, verbose_name='Tipe Pembayaran')),
                ('deskripsi', models.TextField(blank=True, null=True, verbose_name='Deskripsi')),
                ('gambar', models.ImageField(blank=True, null=True, upload_to='metode_pembayaran/', validators=[apps.core.validators.validate_image_file], verbose_name='Gambar')),
                ('saldo', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Saldo')),
                ('aktif', models.BooleanField(default=True, verbose_name='Aktif')),
                ('dibuat_pada', models.DateTimeField(auto_now_add=True, verbose_name='Dibuat Pada')),
                ('diubah_pada', models.DateTimeField(auto_now=True, verbose_name='Diubah Pada')),
                ('akun_kas_bank', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='metode_pembayaran', to='akuntansi.akun', verbose_name='Akun CoA Kas/Bank')),
                ('kas_bank_account', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='metode_pembayaran', to='kas_bank.kasbankaccount', verbose_name='Akun Kas/Bank')),
            ],
            options={
                'verbose_name': 'Metode Pembayaran',
                'verbose_name_plural': 'Metode Pembayaran',
                'ordering': ['nama'],
            },
        ),
        migrations.CreateModel(
            name='POSTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nomor_transaksi', models.CharField(max_length=50, unique=True, verbose_name='Nomor Transaksi')),
                ('tanggal', models.DateTimeField(auto_now_add=True, verbose_name='Tanggal')),
                ('nama_customer', models.CharField(blank=True, max_length=200, null=True, verbose_name='Nama Customer')),
                ('subtotal', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Subtotal')),
                ('diskon', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Diskon')),
                ('pajak', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Pajak')),
                ('total_harga', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Total Harga')),
                ('jumlah_bayar', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Jumlah Bayar')),
                ('kembalian', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Kembalian')),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('unpaid', 'Belum Lunas'), ('paid', 'Lunas'), ('cancelled', 'Dibatalkan')], default='paid', max_length=20, verbose_name='Status')),
                ('jatuh_tempo', models.DateField(blank=True, null=True, verbose_name='Jatuh Tempo')),
                ('catatan', models.TextField(blank=True, null=True, verbose_name='Catatan')),
                ('dibuat_pada', models.DateTimeField(auto_now_add=True)),
        ('customer', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pos_transactions', to='penjualan.customer', verbose_name='Customer')),
                ('gudang', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='pos_transactions', to='produk.gudang', verbose_name='Gudang')),
                ('kasir', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='pos_transactions', to=settings.AUTH_USER_MODEL, verbose_name='Kasir')),
                ('metode_pembayaran', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='pos.metodepembayaran', verbose_name='Metode Pembayaran')),
            ],
            options={
                'verbose_name': 'Transaksi POS',
                'verbose_name_plural': 'Transaksi POS',
                'ordering': ['-dibuat_pada'],
            },
        ),
        migrations.AddField(
            model_name='postransactionitem',
            name='produk',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='produk.produk', verbose_name='Produk'),
        ),
        migrations.AddField(
            model_name='postransactionitem',
            name='satuan_transaksi',
            field=models.ForeignKey(blank=True, help_text='Kosongkan jika menggunakan satuan asli produk', null=True, on_delete=django.db.models.deletion.SET_NULL, to='produk.satuan', verbose_name='Satuan Transaksi'),
        ),
        migrations.AddField(
            model_name='postransactionitem',
            name='transaction',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='pos.postransaction', verbose_name='Transaksi'),
        ),
        migrations.AddIndex(
            model_name='metodepembayaran',
            index=models.Index(fields=['aktif', 'nama'], name='pos_pay_aktif_nama_idx'),
        ),
        migrations.AddIndex(
            model_name='metodepembayaran',
            index=models.Index(fields=['aktif', 'kode'], name='pos_pay_aktif_kode_idx'),
        ),
        migrations.AddIndex(
            model_name='postransaction',
            index=models.Index(fields=['tanggal', 'status'], name='pos_trx_tgl_status_idx'),
        ),
        migrations.AddIndex(
            model_name='postransaction',
            index=models.Index(fields=['gudang', 'tanggal'], name='pos_trx_gdg_tgl_idx'),
        ),
        migrations.AddIndex(
            model_name='postransaction',
            index=models.Index(fields=['kasir', 'tanggal'], name='pos_trx_kasir_tgl_idx'),
        ),
        migrations.AddIndex(
            model_name='postransaction',
            index=models.Index(fields=['metode_pembayaran', 'status'], name='pos_trx_pay_status_idx'),
        ),
        migrations.AddIndex(
            model_name='postransaction',
            index=models.Index(fields=['customer', 'status'], name='pos_trx_cust_status_idx'),
        ),
        migrations.AddIndex(
            model_name='postransactionitem',
            index=models.Index(fields=['produk', 'transaction'], name='pos_item_prod_trx_idx'),
        ),
    ]
