"""
==========================================================================
 Management Command: backup_reimburse
 ==========================================================================
 Backup semua data ReimburseRequest + ReimburseItem ke file JSON.
 
 Penggunaan:
   python manage.py backup_reimburse
   python manage.py backup_reimburse --output=backup_reimburse_20260802.json
 
 Output: File JSON dengan struktur:
 {
   "metadata": { "tanggal_backup": "...", "total_request": N, "total_item": N },
   "requests": [ { request fields + "items": [...] }, ... ]
 }
 
 Idempotent: Tidak mengubah database, hanya membaca.
 Overwrite: File output akan ditimpa jika sudah ada.
==========================================================================
"""
import json
import os
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from apps.reimburse.models import ReimburseRequest


class Command(BaseCommand):
    help = 'Backup seluruh data Reimburse ke file JSON'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output', '-o',
            type=str,
            default=None,
            help='Path file output (default: backup_reimburse_YYYYMMDD_HHMMSS.json di project root)',
        )

    def handle(self, *args, **options):
        output = options['output']
        if not output:
            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            output = f'backup_reimburse_{timestamp}.json'

        total_request = 0
        total_item = 0
        requests_data = []

        for req in ReimburseRequest.objects.prefetch_related('items').order_by('pk'):
            total_request += 1
            items = []
            for item in req.items.all():
                total_item += 1
                items.append({
                    'kategori_id': item.kategori_id,
                    'deskripsi': item.deskripsi,
                    'nominal': str(item.nominal),
                    'bukti': item.bukti.name if item.bukti else None,
                })
            requests_data.append({
                'nomor': req.nomor,
                'pemohon_id': req.pemohon_id,
                'tanggal': str(req.tanggal),
                'keterangan': req.keterangan,
                'total': str(req.total),
                'status': req.status,
                'approved_by_id': req.approved_by_id,
                'approved_at': str(req.approved_at) if req.approved_at else None,
                'rejection_reason': req.rejection_reason,
                'metode_pembayaran_id': req.metode_pembayaran_id,
                'tanggal_bayar': str(req.tanggal_bayar) if req.tanggal_bayar else None,
                'cancelled_by_id': req.cancelled_by_id,
                'cancelled_at': str(req.cancelled_at) if req.cancelled_at else None,
                'dibuat_oleh_id': req.dibuat_oleh_id,
                'dibuat_pada': str(req.dibuat_pada),
                'diupdate_pada': str(req.diupdate_pada),
                'items': items,
            })

        backup_data = {
            'metadata': {
                'tanggal_backup': timezone.now().isoformat(),
                'total_request': total_request,
                'total_item': total_item,
            },
            'requests': requests_data,
        }

        with open(output, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2, cls=DjangoJSONEncoder)

        file_size = os.path.getsize(output)
        self.stdout.write(
            self.style.SUCCESS(
                f'Backup Reimburse selesai.\n'
                f'  File    : {output}\n'
                f'  Size    : {file_size:,} bytes\n'
                f'  Request : {total_request}\n'
                f'  Item    : {total_item}'
            )
        )
