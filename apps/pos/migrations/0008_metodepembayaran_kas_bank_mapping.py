from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("akuntansi", "0001_initial"),
        ("kas_bank", "0001_initial"),
        ("pos", "0007_add_satuan_transaksi_jumlah_konversi_to_postransactionitem"),
    ]

    operations = [
        migrations.AddField(
            model_name="metodepembayaran",
            name="akun_kas_bank",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="metode_pembayaran",
                to="akuntansi.akun",
                verbose_name="Akun CoA Kas/Bank",
            ),
        ),
        migrations.AddField(
            model_name="metodepembayaran",
            name="kas_bank_account",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="metode_pembayaran",
                to="kas_bank.kasbankaccount",
                verbose_name="Akun Kas/Bank",
            ),
        ),
    ]
