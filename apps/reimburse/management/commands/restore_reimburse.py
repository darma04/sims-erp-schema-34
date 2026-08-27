"""
==========================================================================
 Management Command: restore_reimburse
 ==========================================================================
 Restore data Reimburse dari file JSON hasil backup_reimburse.
 
 Penggunaan:
   python manage.py restore_reimburse backup_reimburse_20260802.json
   python manage.py restore_reimburse backup.json --dry-run
   python manage.py restore_reimburse backup.json --force
 
 Mode:
   --dry-run  : Tampilkan apa yang akan direstore tanpa eksekusi.
   --force    : Lewati konfirmasi.
 
 Safety:
   - Hanya restore request dengan status 'cancelled' / 'completed' (final).
   - Request dengan status aktif (draft/submitted/approved/paid) di-SKIP
     karena bisa konflik dengan data yang sedang berjalan.
   - Nomor reimburse dipertahankan dari backup.
   - Items tidak direstore jika request sudah ada (guard duplikasi).
 
 ⚠️  PERINGATAN: Jurnal akuntansi TIDAK dibuat ulang saat restore.
    Data keuangan yang sudah di-jurnal di sistem lama harus diverifikasi
    secara terpisah melalui modul Akuntansi.
==========================================================================
"""
import json
import sys
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.reimburse.models import ReimburseRequest, ReimburseItem


class Command(BaseCommand):
    help = 'Restore data Reimburse dari file JSON backup'

    def add_arguments(self, parser):
        parser.add_argument('file', type=str, help='Path file JSON backup')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Tampilkan rencana restore tanpa eksekusi',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Lewati konfirmasi',
        )

    def handle(self, *args, **options):
        filepath = options['file']
        dry_run = options['dry_run']
        force = options['force']

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f'File tidak ditemukan: {filepath}'))
            sys.exit(1)
        except json.JSONDecodeError as e:
            self.stderr.write(self.style.ERROR(f'Format JSON tidak valid: {e}'))
            sys.exit(1)

        metadata = data.get('metadata', {})
        requests_data = data.get('requests', [])

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"  RESTORE REIMBURSE")
        self.stdout.write(f"{'='*60}")
        self.stdout.write(f"  File          : {filepath}")
        self.stdout.write(f"  Tanggal Backup: {metadata.get('tanggal_backup', 'N/A')}")
        self.stdout.write(f"  Total Request : {metadata.get('total_request', 0)}")
        self.stdout.write(f"  Total Item    : {metadata.get('total_item', 0)}")
        self.stdout.write(f"  Mode          : {'DRY-RUN' if dry_run else 'LIVE'}")
        self.stdout.write(f"{'='*60}\n")

        # ── Analisa data ──
        skipped_non_final = []
        skipped_exists = []
        to_restore = []
        to_restore_items = 0

        for req_data in requests_data:
            status = req_data.get('status', '')
            nomor = req_data.get('nomor', '?')
            if status not in ('cancelled', 'completed'):
                skipped_non_final.append((nomor, status))
                continue
            if ReimburseRequest.objects.filter(nomor=nomor).exists():
                skipped_exists.append(nomor)
                continue
            to_restore.append(req_data)
            to_restore_items += len(req_data.get('items', []))

        self.stdout.write(f"  [SKIP] Status non-final: {len(skipped_non_final)}")
        for n, s in skipped_non_final[:5]:
            self.stdout.write(f"      - {n} [{s}]")
        if len(skipped_non_final) > 5:
            self.stdout.write(f"      ... dan {len(skipped_non_final)-5} lainnya")

        self.stdout.write(f"  [SKIP] Sudah ada di DB:    {len(skipped_exists)}")
        for n in skipped_exists[:5]:
            self.stdout.write(f"      - {n}")
        if len(skipped_exists) > 5:
            self.stdout.write(f"      ... dan {len(skipped_exists)-5} lainnya")

        self.stdout.write(f"  [OK] Akan direstore:         {len(to_restore)} request, {to_restore_items} items\n")

        if not to_restore:
            self.stdout.write(self.style.WARNING('Tidak ada data yang perlu direstore.'))
            return

        if dry_run:
            self.stdout.write(self.style.SUCCESS('[DRY-RUN] Selesai. Tidak ada perubahan pada database.'))
            return

        if not force:
            confirm = input('Lanjutkan restore? (ya/tidak): ').strip().lower()
            if confirm not in ('ya', 'y', 'yes'):
                self.stdout.write(self.style.WARNING('Restore dibatalkan.'))
                return

        # ── Eksekusi restore ──
        restored_count = 0
        errors = []

        with db_transaction.atomic():
            for req_data in to_restore:
                try:
                    items_data = req_data.pop('items', [])
                    req = ReimburseRequest(
                        nomor=req_data['nomor'],
                        pemohon_id=req_data.get('pemohon_id'),
                        tanggal=req_data['tanggal'],
                        keterangan=req_data.get('keterangan', ''),
                        total=Decimal(req_data.get('total', '0')),
                        status=req_data.get('status', 'cancelled'),
                        approved_by_id=req_data.get('approved_by_id'),
                        approved_at=req_data.get('approved_at') or None,
                        rejection_reason=req_data.get('rejection_reason', ''),
                        metode_pembayaran_id=req_data.get('metode_pembayaran_id'),
                        tanggal_bayar=req_data.get('tanggal_bayar') or None,
                        cancelled_by_id=req_data.get('cancelled_by_id'),
                        cancelled_at=req_data.get('cancelled_at') or None,
                        dibuat_oleh_id=req_data.get('dibuat_oleh_id'),
                    )
                    req.save()
                    for item_data in items_data:
                        ReimburseItem.objects.create(
                            request=req,
                            kategori_id=item_data.get('kategori_id'),
                            deskripsi=item_data.get('deskripsi', ''),
                            nominal=Decimal(item_data.get('nominal', '0')),
                        )
                    restored_count += 1
                except Exception as e:
                    errors.append((req_data.get('nomor', '?'), str(e)))

        self.stdout.write(self.style.SUCCESS(f'\nRestore selesai: {restored_count} request berhasil.'))
        if errors:
            self.stdout.write(self.style.ERROR(f'{len(errors)} error:'))
            for nomor, err in errors:
                self.stdout.write(f'  - {nomor}: {err}')
