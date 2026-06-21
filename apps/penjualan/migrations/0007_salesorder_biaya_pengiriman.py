from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('penjualan', '0006_salesorderitem_hpp_snapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='salesorder',
            name='biaya_pengiriman',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Biaya Pengiriman/Ongkir'),
        ),
    ]
