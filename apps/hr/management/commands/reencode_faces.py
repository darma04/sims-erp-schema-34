"""
Management command: Re-encode semua foto wajah terdaftar
menggunakan algoritma LBPH terbaru.

Usage: python manage.py reencode_faces
"""
from django.core.management.base import BaseCommand
from apps.hr.models import FotoWajah
from apps.hr import face_utils
import json


class Command(BaseCommand):
    help = 'Re-encode semua foto wajah dengan algoritma LBPH terbaru'

    def handle(self, *args, **options):
        fotos = FotoWajah.objects.filter(aktif=True)
        total = fotos.count()
        success = 0
        failed = 0

        self.stdout.write(f"Memproses {total} foto wajah...")

        for foto in fotos:
            # Cek apakah sudah pakai encoding v2
            try:
                enc = json.loads(foto.encoding) if foto.encoding else {}
                if enc.get('version') == 2:
                    self.stdout.write(f"  [SKIP] #{foto.pk} {foto.karyawan.nama} - sudah v2")
                    success += 1
                    continue
            except (json.JSONDecodeError, Exception):
                pass

            # Re-encode dari file foto
            if foto.foto and foto.foto.name:
                try:
                    new_encoding = face_utils.encode_face_from_file(foto.foto)
                    if new_encoding:
                        foto.encoding = new_encoding
                        foto.save(update_fields=['encoding'])
                        self.stdout.write(self.style.SUCCESS(
                            f"  [OK] #{foto.pk} {foto.karyawan.nama} - re-encoded"
                        ))
                        success += 1
                    else:
                        self.stdout.write(self.style.WARNING(
                            f"  [WARN] #{foto.pk} {foto.karyawan.nama} - wajah tidak terdeteksi"
                        ))
                        failed += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(
                        f"  [ERR] #{foto.pk} {foto.karyawan.nama} - {str(e)}"
                    ))
                    failed += 1
            else:
                self.stdout.write(self.style.WARNING(
                    f"  [WARN] #{foto.pk} {foto.karyawan.nama} - file foto tidak ditemukan"
                ))
                failed += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nSelesai! {success}/{total} berhasil, {failed} gagal."
        ))
