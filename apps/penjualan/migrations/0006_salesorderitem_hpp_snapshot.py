from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("penjualan", "0005_performance_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="salesorderitem",
            name="hpp_satuan",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name="HPP Satuan"),
        ),
        migrations.AddField(
            model_name="salesorderitem",
            name="hpp_subtotal",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name="Subtotal HPP"),
        ),
    ]
