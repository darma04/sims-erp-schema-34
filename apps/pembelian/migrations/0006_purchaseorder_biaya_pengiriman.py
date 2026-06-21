from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pembelian', '0005_performance_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseorder',
            name='biaya_pengiriman',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Biaya Pengiriman/Ongkir'),
        ),
    ]
