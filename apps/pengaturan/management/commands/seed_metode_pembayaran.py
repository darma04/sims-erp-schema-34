from django.core.management.base import BaseCommand

from apps.pengaturan.payment_seed import seed_default_payment_methods


class Command(BaseCommand):
    help = "Seed metode pembayaran default dan lengkapi relasi default cabang/produk."

    def handle(self, *args, **options):
        stats = seed_default_payment_methods()
        self.stdout.write(self.style.SUCCESS("Seed metode pembayaran default selesai."))
        for key, value in stats.items():
            self.stdout.write(f"{key}: {value}")
