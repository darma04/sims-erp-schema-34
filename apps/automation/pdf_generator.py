"""
==========================================================================
 PDF GENERATOR - Generate PDF dari Template Cetak Django untuk Telegram
==========================================================================
 Menggunakan Django template engine untuk render template cetak yang SAMA
 dengan halaman cetak browser, lalu convert ke PDF via xhtml2pdf.

 PENTING:
 - close_old_connections() dipanggil sebelum akses DB di background thread
   agar tidak terjadi error koneksi stale (intermittent failure).
 - HTML dibersihkan dari element yang tidak didukung xhtml2pdf sebelum convert.
 - Jika template render gagal, fallback HTML sederhana digunakan.

 Fungsi:
 - generate_pos_pdf(instance)            → PDF Invoice POS
 - generate_sales_order_pdf(instance)    → PDF Sales Order
 - generate_purchase_order_pdf(instance) → PDF Purchase Order
 - generate_biaya_pdf(instance)          → PDF Bukti Pengeluaran
 - generate_penggajian_pdf(instance)     → PDF Slip Gaji
==========================================================================
"""

import os
import re
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _ensure_db_connection():
    """Pastikan koneksi database fresh di background thread."""
    from django.db import close_old_connections
    close_old_connections()


def _render_django_template(template_name, context):
    """
    Render template cetak Django ke string HTML menggunakan render_to_string.
    Ini SAMA persis dengan yang di-render browser saat user klik Cetak.

    Di VPS (background thread), request object tidak tersedia.
    Beberapa template membutuhkan context processor (request, csrf, dll).
    Kita gunakan RequestFactory untuk membuat dummy request jika diperlukan.
    """
    from django.template.loader import render_to_string
    try:
        # Coba render dengan request=None (cukup untuk template cetak sederhana)
        return render_to_string(template_name, context)
    except Exception as e:
        # Jika gagal karena butuh request context, coba dengan dummy request
        logger.warning(f"[PDF] Template render gagal tanpa request: {e}, mencoba dengan dummy request")
        try:
            from django.test import RequestFactory
            factory = RequestFactory()
            dummy_request = factory.get('/')
            # Tambahkan user anonymous jika diperlukan
            from django.contrib.auth.models import AnonymousUser
            dummy_request.user = AnonymousUser()
            return render_to_string(template_name, context, request=dummy_request)
        except Exception as e2:
            logger.error(f"[PDF] Template render gagal total: {e2}", exc_info=True)
            raise


def _clean_html_for_pdf(html_content):
    """
    Bersihkan HTML dari elemen yang tidak didukung xhtml2pdf:
    - Hapus onload="window.print()"
    - Hapus <script> blocks
    - Konversi <span> status badge menjadi <table><td> dengan inline styles
      karena xhtml2pdf tidak merender padding/background pada elemen inline <span>.
    """
    # Hapus onload="window.print()"
    html_content = html_content.replace('onload="window.print()"', '')

    # Hapus semua <script>...</script> blocks
    import re
    html_content = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)

    # === STATUS TEXT CONVERTER ===
    # xhtml2pdf tidak bisa merender badge <span> dengan padding/background.
    # Konversi ke teks biasa yang sifatnya neutral (TIDAK BERWARNA warni)
    def _replace_badge(match):
        classes = match.group(1)
        text = match.group(2)
        return (
            f'<div style="text-align: right; font-weight: bold; font-size: 12px; '
            f'color: #333333; text-transform: uppercase; letter-spacing: 0.5px; '
            f'margin-top: 5px;">{text}</div>'
        )

    html_content = re.sub(
        r'<span class="([^">]*?(?:invoice|order|po|slip|biaya)-status[^">]*?)">(.*?)</span>',
        _replace_badge,
        html_content,
        flags=re.DOTALL
    )

    return html_content


def _link_callback(uri, rel):
    """
    Callback untuk xhtml2pdf agar bisa resolve path lokal (media & static).
    xhtml2pdf tidak bisa mengakses URL relatif seperti /media/perusahaan/logo.png,
    maka kita konversi ke path absolut di filesystem.
    """
    from django.conf import settings
    import urllib.parse

    # Unquote URL (misal: %20 menjadi spasi)
    uri = urllib.parse.unquote(uri)

    # Jika sudah file:// URI, strip prefix dan return
    if uri.startswith('file:///'):
        path = uri[8:] if os.name == 'nt' else uri[7:]
        return os.path.normpath(path)
    if uri.startswith('file://'):
        path = uri[7:]
        return os.path.normpath(path)

    # Mapping URI prefix ke direktori lokal
    media_url = getattr(settings, 'MEDIA_URL', '/media/')
    static_url = getattr(settings, 'STATIC_URL', '/static/')
    media_root = str(getattr(settings, 'MEDIA_ROOT', ''))
    static_root = str(getattr(settings, 'STATIC_ROOT', ''))

    # Coba resolve /media/... ke MEDIA_ROOT
    if uri.startswith(media_url):
        path = os.path.join(media_root, uri[len(media_url):])
        if os.path.isfile(path):
            return os.path.normpath(path)

    # Coba resolve /static/... ke STATIC_ROOT atau STATICFILES_DIRS
    if uri.startswith(static_url):
        relative = uri[len(static_url):]
        # Coba STATIC_ROOT dulu
        path = os.path.join(static_root, relative)
        if os.path.isfile(path):
            return os.path.normpath(path)
        # Coba setiap STATICFILES_DIRS
        for sdir in getattr(settings, 'STATICFILES_DIRS', []):
            path = os.path.join(str(sdir), relative)
            if os.path.isfile(path):
                return os.path.normpath(path)

    # Jika path absolut di filesystem langsung
    if os.path.isfile(uri):
        return os.path.normpath(uri)

    # Gagal resolve → return URI asli (xhtml2pdf akan skip gambar)
    logger.warning(f"[PDF] Gagal resolve URI: {uri}")
    return uri


def _fix_logo_paths(html_content):
    """
    Konversi URL logo relatif (/media/...) ke path absolut file:///
    agar xhtml2pdf bisa menemukan file gambar di filesystem lokal.
    Ini sebagai pendekatan tambahan selain link_callback.
    """
    from django.conf import settings
    import urllib.parse

    media_url = getattr(settings, 'MEDIA_URL', '/media/')
    media_root = str(getattr(settings, 'MEDIA_ROOT', ''))

    # Ganti src="/media/..." dengan src="file:///absolute/path/..."
    def replace_media_src(match):
        relative_path = match.group(1)
        # Unquote path karena URL mungkin mengandung %20 (spasi)
        relative_path = urllib.parse.unquote(relative_path)
        abs_path = os.path.join(media_root, relative_path)
        if os.path.isfile(abs_path):
            # Normalisasi path untuk OS
            abs_path = abs_path.replace('\\', '/')
            return f'src="file:///{abs_path}"'
        return match.group(0)  # Kembalikan asli jika file tidak ditemukan

    # Pattern: src="/media/relative/path"
    pattern = r'src="' + re.escape(media_url) + r'([^"]+)"'
    html_content = re.sub(pattern, replace_media_src, html_content)

    return html_content


def _html_to_pdf(html_content, filename_prefix):
    """
    Convert HTML string ke file PDF menggunakan xhtml2pdf.
    Menggunakan link_callback untuk resolve path gambar lokal (logo, dsb).
    Return: path file PDF sementara, atau None jika gagal.
    """
    try:
        from xhtml2pdf import pisa
        import io
        from django.conf import settings

        # Buat folder temp_pdf di media
        temp_dir = os.path.join(settings.BASE_DIR, 'media', 'temp_pdf')
        os.makedirs(temp_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = os.path.join(temp_dir, f'{filename_prefix}_{timestamp}.pdf')

        # Bersihkan HTML dari script dan event handlers
        html_content = _clean_html_for_pdf(html_content)

        # Fix path logo agar xhtml2pdf bisa menemukan file gambar
        html_content = _fix_logo_paths(html_content)

        with open(filepath, 'wb') as pdf_file:
            pisa_status = pisa.CreatePDF(
                io.BytesIO(html_content.encode('utf-8')),
                dest=pdf_file,
                encoding='utf-8',
                link_callback=_link_callback  # Resolve path gambar lokal
            )

        if pisa_status.err:
            logger.error(f"[PDF] xhtml2pdf error count: {pisa_status.err}")
            # Tetap return filepath jika file berhasil ditulis (partial PDF)
            if os.path.exists(filepath) and os.path.getsize(filepath) > 100:
                return filepath
            return None

        return filepath

    except ImportError:
        logger.error("[PDF] xhtml2pdf belum terinstall. Jalankan: pip install xhtml2pdf")
        return None
    except Exception as e:
        logger.error(f"[PDF] Error generate PDF: {e}", exc_info=True)
        return None


def _get_template_cetak(jenis):
    """Ambil TemplateCetak dari database."""
    try:
        from apps.pengaturan.models import TemplateCetak
        return TemplateCetak.get_template(jenis)
    except Exception:
        return None


def generate_pos_pdf(instance):
    """
    Generate PDF Invoice POS menggunakan template cetak YANG SAMA
    dengan halaman cetak browser (pos/invoice_print.html).
    """
    try:
        _ensure_db_connection()
        instance.refresh_from_db()
        template = _get_template_cetak('invoice')

        # Ambil data perusahaan untuk logo di header
        try:
            from apps.pengaturan.models import PengaturanPerusahaan
            perusahaan = PengaturanPerusahaan.load()
        except Exception:
            perusahaan = None

        context = {
            'transaction': instance,
            'perusahaan': perusahaan,
            'template': template,
        }

        html = _render_django_template('pos/invoice_print.html', context)
        nomor = instance.nomor_transaksi.replace('/', '_')
        return _html_to_pdf(html, f"POS_{nomor}")

    except Exception as e:
        logger.error(f"[PDF] Error generate POS PDF: {e}", exc_info=True)
        return None


def generate_sales_order_pdf(instance):
    """
    Generate PDF Sales Order menggunakan template cetak YANG SAMA
    dengan halaman cetak browser (penjualan/sales_order_print.html).
    """
    try:
        _ensure_db_connection()
        instance.refresh_from_db()
        template = _get_template_cetak('sales_order')

        # Ambil data perusahaan untuk logo di header
        try:
            from apps.pengaturan.models import PengaturanPerusahaan
            perusahaan = PengaturanPerusahaan.load()
        except Exception:
            perusahaan = None

        context = {
            'sales_order': instance,
            'perusahaan': perusahaan,
            'template': template,
        }

        html = _render_django_template('penjualan/sales_order_print.html', context)
        nomor = instance.nomor_so.replace('/', '_')
        return _html_to_pdf(html, f"SO_{nomor}")

    except Exception as e:
        logger.error(f"[PDF] Error generate SO PDF: {e}", exc_info=True)
        return None


def generate_purchase_order_pdf(instance):
    """
    Generate PDF Purchase Order menggunakan template cetak YANG SAMA
    dengan halaman cetak browser (pembelian/purchase_order_print.html).
    """
    try:
        _ensure_db_connection()
        instance.refresh_from_db()
        template = _get_template_cetak('purchase_order')

        # Ambil data perusahaan untuk logo di header
        try:
            from apps.pengaturan.models import PengaturanPerusahaan
            perusahaan = PengaturanPerusahaan.load()
        except Exception:
            perusahaan = None

        context = {
            'purchase_order': instance,
            'perusahaan': perusahaan,
            'template': template,
        }

        html = _render_django_template('pembelian/purchase_order_print.html', context)
        nomor = instance.nomor_po.replace('/', '_')
        return _html_to_pdf(html, f"PO_{nomor}")

    except Exception as e:
        logger.error(f"[PDF] Error generate PO PDF: {e}", exc_info=True)
        return None


def generate_biaya_pdf(instance):
    """
    Generate PDF Bukti Pengeluaran / Biaya menggunakan template cetak YANG SAMA
    dengan halaman cetak browser (biaya/transaksi_biaya_print.html).
    Context: 'transaksi', 'perusahaan', 'template' (jenis='expense')
    """
    try:
        _ensure_db_connection()
        instance.refresh_from_db()
        template = _get_template_cetak('expense')

        # Ambil data perusahaan (sama seperti TransaksiBiayaPrintView)
        try:
            from apps.pengaturan.models import PengaturanPerusahaan
            perusahaan = PengaturanPerusahaan.load()
        except Exception:
            perusahaan = None

        context = {
            'transaksi': instance,
            'perusahaan': perusahaan,
            'template': template,
        }

        try:
            html = _render_django_template('biaya/transaksi_biaya_print.html', context)
        except Exception:
            # Fallback terakhir: generate HTML sederhana
            html = _generate_biaya_html(instance, template)

        nomor = instance.nomor_transaksi.replace('/', '_')
        return _html_to_pdf(html, f"BIAYA_{nomor}")

    except Exception as e:
        logger.error(f"[PDF] Error generate Biaya PDF: {e}", exc_info=True)
        return None


def generate_penggajian_pdf(instance):
    """
    Generate PDF Slip Gaji menggunakan template cetak YANG SAMA
    dengan halaman cetak browser (hr/penggajian_print.html).
    Context: 'slip', 'template' (jenis='slip_gaji')
    """
    try:
        _ensure_db_connection()
        instance.refresh_from_db()
        template = _get_template_cetak('slip_gaji')

        # Ambil data perusahaan untuk logo di header
        try:
            from apps.pengaturan.models import PengaturanPerusahaan
            perusahaan = PengaturanPerusahaan.load()
        except Exception:
            perusahaan = None

        context = {
            'slip': instance,
            'perusahaan': perusahaan,
            'template': template,
        }

        try:
            html = _render_django_template('hr/penggajian_print.html', context)
        except Exception:
            # Fallback: generate HTML sederhana
            html = _generate_slip_gaji_html(instance, template)

        return _html_to_pdf(html, f"GAJI_{instance.karyawan.nik}_{instance.periode_bulan}_{instance.periode_tahun}")

    except Exception as e:
        logger.error(f"[PDF] Error generate Gaji PDF: {e}", exc_info=True)
        return None


def _format_rupiah(angka):
    """Format angka ke Rupiah."""
    try:
        return f"Rp {float(angka):,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "Rp 0"


def _generate_biaya_html(instance, template):
    """Fallback HTML generator untuk Biaya jika template Django tidak ada."""
    company = template if template else type('obj', (object,), {
        'header_nama_perusahaan': 'SERPTECH', 'header_alamat': '', 'header_telepon': '',
        'header_email': '', 'footer_ucapan': '', 'footer_keterangan': '',
        'signature_kiri_label': 'Disetujui', 'signature_kanan_label': 'Dibuat Oleh',
    })()

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Biaya {instance.nomor_transaksi}</title>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family:Arial,sans-serif; font-size:12px; color:#333; padding:20px; }}
        .container {{ max-width:800px; margin:0 auto; padding:30px; border:1px solid #ddd; }}
        .header {{ border-bottom:3px solid #696cff; padding-bottom:15px; margin-bottom:20px; }}
        .company {{ font-size:22px; font-weight:bold; color:#696cff; }}
        .details {{ font-size:10px; color:#666; }}
        .title {{ font-size:28px; color:#696cff; text-align:right; }}
        .info {{ margin-bottom:20px; }}
        .info-label {{ font-weight:bold; display:inline-block; width:140px; }}
        .amount {{ text-align:center; font-size:20px; font-weight:bold; color:#696cff;
                   border:2px solid #696cff; padding:15px; margin:20px 0; }}
        .footer {{ margin-top:40px; border-top:1px solid #ddd; padding-top:15px; text-align:center; font-size:10px; color:#666; }}
    </style></head><body><div class="container">
        <table width="100%"><tr>
            <td><div class="company">{company.header_nama_perusahaan}</div>
            <div class="details">{company.header_alamat}<br>Telp: {company.header_telepon}<br>Email: {company.header_email}</div></td>
            <td align="right"><div class="title">BUKTI PENGELUARAN</div><div style="color:#666;">#{instance.nomor_transaksi}</div></td>
        </tr></table>
        <hr style="border:none;border-top:3px solid #696cff;margin:15px 0;">
        <div class="info">
            <div><span class="info-label">Tanggal:</span> {instance.tanggal.strftime('%d %B %Y') if instance.tanggal else '-'}</div>
            <div><span class="info-label">Kategori:</span> {instance.kategori or '-'}</div>
            <div><span class="info-label">Deskripsi:</span> {instance.deskripsi or '-'}</div>
            <div><span class="info-label">Metode Bayar:</span> {instance.metode_pembayaran or '-'}</div>
        </div>
        <div class="amount">JUMLAH: {_format_rupiah(instance.jumlah)}</div>
        <div class="footer"><p>{company.footer_ucapan}</p><p>{company.footer_keterangan}</p></div>
    </div></body></html>"""


def _generate_slip_gaji_html(instance, template):
    """Fallback HTML generator untuk Slip Gaji jika template Django tidak ada."""
    company = template if template else type('obj', (object,), {
        'header_nama_perusahaan': 'SERPTECH', 'header_alamat': '', 'header_telepon': '',
        'header_email': '', 'footer_ucapan': '', 'footer_keterangan': '',
        'signature_kiri_label': 'Diterima', 'signature_kanan_label': 'Manager HRD',
    })()

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Slip Gaji {instance.karyawan.nama}</title>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family:Arial,sans-serif; font-size:12px; color:#333; padding:20px; }}
        .container {{ max-width:800px; margin:0 auto; padding:30px; border:1px solid #ddd; }}
        .company {{ font-size:22px; font-weight:bold; color:#696cff; }}
        .details {{ font-size:10px; color:#666; }}
        .info-label {{ font-weight:bold; display:inline-block; width:160px; }}
        table.items {{ width:100%; border-collapse:collapse; margin:10px 0; }}
        table.items th {{ background:#f8f9fa; border-bottom:2px solid #696cff; padding:8px; text-align:left; font-size:10px; text-transform:uppercase; }}
        table.items td {{ padding:6px 8px; border-bottom:1px solid #eee; font-size:10px; }}
        .text-right {{ text-align:right; }}
        .amount {{ text-align:center; font-size:18px; font-weight:bold; color:#696cff;
                   border:2px solid #696cff; padding:12px; margin:15px 0; }}
        .footer {{ margin-top:40px; border-top:1px solid #ddd; padding-top:15px; text-align:center; font-size:10px; color:#666; }}
    </style></head><body><div class="container">
        <table width="100%"><tr>
            <td><div class="company">{company.header_nama_perusahaan}</div>
            <div class="details">{company.header_alamat}<br>Telp: {company.header_telepon}<br>Email: {company.header_email}</div></td>
            <td align="right"><div style="font-size:26px;color:#696cff;font-weight:bold;">SLIP GAJI</div>
            <div style="color:#666;">Periode: {instance.periode}</div></td>
        </tr></table>
        <hr style="border:none;border-top:3px solid #696cff;margin:15px 0;">
        <div style="margin-bottom:15px;">
            <div><span class="info-label">NIK:</span> {instance.karyawan.nik}</div>
            <div><span class="info-label">Nama:</span> {instance.karyawan.nama}</div>
            <div><span class="info-label">Jabatan:</span> {instance.karyawan.jabatan.nama if instance.karyawan.jabatan else '-'}</div>
        </div>
        <table class="items"><thead><tr><th colspan="2" style="background:#e8f5e9;color:#155724;text-align:center;">PENDAPATAN</th></tr></thead><tbody>
            <tr><td>Gaji Pokok</td><td class="text-right">{_format_rupiah(instance.gaji_pokok)}</td></tr>
            <tr><td>Tunjangan Jabatan</td><td class="text-right">{_format_rupiah(instance.tunjangan_jabatan)}</td></tr>
            <tr><td>Tunjangan Makan</td><td class="text-right">{_format_rupiah(instance.tunjangan_makan)}</td></tr>
            <tr><td>Tunjangan Transport</td><td class="text-right">{_format_rupiah(instance.tunjangan_transport)}</td></tr>
            <tr><td>Tunjangan Lainnya</td><td class="text-right">{_format_rupiah(instance.tunjangan_lainnya)}</td></tr>
            <tr><td>Lembur</td><td class="text-right">{_format_rupiah(instance.lembur)}</td></tr>
            <tr><td>Bonus</td><td class="text-right">{_format_rupiah(instance.bonus)}</td></tr>
            <tr style="font-weight:bold;background:#e8f5e9;"><td>Total Pendapatan</td><td class="text-right">{_format_rupiah(instance.total_pendapatan)}</td></tr>
        </tbody></table>
        <table class="items"><thead><tr><th colspan="2" style="background:#ffebee;color:#721c24;text-align:center;">POTONGAN</th></tr></thead><tbody>
            <tr><td>BPJS Kesehatan</td><td class="text-right">{_format_rupiah(instance.potongan_bpjs_kesehatan)}</td></tr>
            <tr><td>BPJS Ketenagakerjaan</td><td class="text-right">{_format_rupiah(instance.potongan_bpjs_ketenagakerjaan)}</td></tr>
            <tr><td>PPh 21</td><td class="text-right">{_format_rupiah(instance.potongan_pph21)}</td></tr>
            <tr><td>Potongan Lainnya</td><td class="text-right">{_format_rupiah(instance.potongan_lainnya)}</td></tr>
            <tr style="font-weight:bold;background:#ffebee;"><td>Total Potongan</td><td class="text-right">{_format_rupiah(instance.total_potongan)}</td></tr>
        </tbody></table>
        <div class="amount">GAJI BERSIH: {_format_rupiah(instance.gaji_bersih)}</div>
        <div class="footer"><p>{company.footer_ucapan}</p><p>{company.footer_keterangan}</p></div>
    </div></body></html>"""


def cleanup_pdf(filepath):
    """Hapus file PDF sementara setelah selesai dikirim."""
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
    except Exception as e:
        logger.warning(f"[PDF] Gagal hapus file temp: {e}")
