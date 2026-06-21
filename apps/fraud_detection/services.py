"""
==========================================================================
 FRAUD DETECTION SERVICES — Deteksi Kecurangan Real-time
==========================================================================
 Service layer untuk deteksi kecurangan otomatis.

 Aturan Deteksi:
 1. Diskon > 30% tanpa approval manager → FraudAlert
 2. Harga jual < Harga beli (Negative Margin) → FraudAlert
 3. Stok menjadi negatif (layer aplikasi) → FraudAlert
 4. Transaksi dengan nilai di atas threshold → FraudAlert
 5. Penggunaan sparepart berlebihan → FraudAlert (di signals.py)

 Setiap aturan mengembalikan FraudAlert yang sudah tersimpan.
==========================================================================
"""
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


class FraudDetectionService:
    """
    Service untuk deteksi kecurangan real-time.

    Cara pakai:
        FraudDetectionService.evaluate(transaction, user)
        # → Menjalankan semua aturan, return list of FraudAlert
    """

    @classmethod
    def evaluate(cls, transaction, user=None, invoice=None):
        """
        Jalankan semua aturan deteksi pada sebuah transaksi.

        Args:
            transaction: Instance model transaksi (POSTransaction, SalesOrder, dll)
            user: User yang melakukan transaksi
            invoice: Instance tagihan/invoice (optional)

        Returns:
            list[FraudAlert]: Daftar alert yang terbuat (kosong jika tidak ada anomali)
        """
        alerts = []
        model_name = type(transaction).__module__ + '.' + type(transaction).__name__
        object_id = str(transaction.pk)

        diskon_alert = cls.check_diskon_berlebihan(transaction, user)
        if diskon_alert:
            alerts.append(diskon_alert)

        nilai_alert = cls.check_transaksi_mencurigakan(transaction, user)
        if nilai_alert:
            alerts.append(nilai_alert)

        if hasattr(transaction, 'items'):
            for item in transaction.items.all():
                if hasattr(item, 'produk') and item.produk:
                    margin_alert = cls.check_negative_margin(item.produk, item, user)
                    if margin_alert:
                        alerts.append(margin_alert)

        for alert in alerts:
            logger.warning(
                f"[FRAUD DETECTED] {alert.get_jenis_display()} — "
                f"{alert.deskripsi[:100]}"
            )

        return alerts

    @classmethod
    def check_diskon_berlebihan(cls, transaction, user=None):
        """
        Deteksi diskon > batas FraudRule.

        Args:
            transaction: Instance transaksi yang memiliki field 'diskon' atau 'total_diskon'
            user: User pelaku transaksi

        Returns:
            FraudAlert or None
        """
        from apps.fraud_detection.models import FraudRule, FraudAlert

        diskon = getattr(transaction, 'diskon', 0) or getattr(transaction, 'total_diskon', 0)
        subtotal = getattr(transaction, 'subtotal', 0) or getattr(transaction, 'total_sebelum_diskon', 0)

        if not subtotal or not diskon:
            return None

        rule = FraudRule.load()
        max_diskon_persen = float(getattr(rule, 'max_discount_percent', 30) or 30)
        diskon_persen = float(diskon) / float(subtotal) * 100

        if diskon_persen > max_diskon_persen:
            return FraudAlert.objects.create(
                jenis='diskon_besar',
                severity='high',
                deskripsi=(
                    f"Diskon {diskon_persen:.1f}% melebihi batas {max_diskon_persen}%. "
                    f"Nilai diskon: Rp {diskon:,.0f} dari subtotal Rp {subtotal:,.0f}. "
                    f"Diinput oleh: {user.get_full_name() or user.username if user else 'Unknown'}."
                ),
                user_terkait=user,
                nominal=diskon,
                model_name=type(transaction).__name__,
                object_id=str(transaction.pk),
            )
        return None

    @classmethod
    def check_negative_margin(cls, produk, item=None, user=None):
        """
        Deteksi harga jual < harga beli (Negative Margin).

        Args:
            produk: Instance Produk
            item: Instance item transaksi (opsional — untuk konteks)
            user: User pelaku (opsional)

        Returns:
            FraudAlert or None
        """
        from apps.fraud_detection.models import FraudRule, FraudAlert

        modal = float(getattr(produk, 'harga_beli', 0) or 0)
        if item:
            harga_jual = float(getattr(item, 'harga_satuan', 0) or getattr(item, 'harga_jual', 0))
        else:
            harga_jual = float(getattr(produk, 'harga_jual', 0) or 0)

        if modal <= 0:
            return None

        rule = FraudRule.load()
        min_margin = float(getattr(rule, 'min_margin_percent', 0) or 0)
        margin_persen = (harga_jual - modal) / modal * 100

        if margin_persen < min_margin:
            severity = 'critical' if harga_jual < modal else 'medium'
            return FraudAlert.objects.create(
                jenis='po_markup' if harga_jual < modal else 'lainnya',
                severity=severity,
                deskripsi=(
                    f"Margin negatif terdeteksi: {produk.nama} (SKU: {produk.sku}) "
                    f"harga jual Rp {harga_jual:,.0f} < harga beli Rp {modal:,.0f} "
                    f"(margin: {margin_persen:.1f}%). "
                    f"Diinput oleh: {user.get_full_name() or user.username if user else 'Unknown'}."
                ),
                user_terkait=user,
                nominal=Decimal(str(harga_jual - modal)),
                model_name=produk.__class__.__name__,
                object_id=str(produk.pk),
            )
        return None

    @classmethod
    def check_transaksi_mencurigakan(cls, transaction, user=None):
        """
        Deteksi transaksi dengan nilai di atas ambang batas wajar.

        Args:
            transaction: Instance transaksi (POS, SO, PO, Biaya)
            user: User pelaku transaksi

        Returns:
            FraudAlert or None
        """
        from apps.fraud_detection.models import FraudRule, FraudAlert

        total = getattr(transaction, 'total', 0) or getattr(transaction, 'grand_total', 0) or getattr(transaction, 'jumlah', 0) or getattr(transaction, 'total_biaya', 0)
        if not total:
            return None

        rule = FraudRule.load()
        threshold = float(getattr(rule, 'max_transaction_amount', 10000000) or 10000000)

        if float(total) > threshold:
            return FraudAlert.objects.create(
                jenis='lainnya',
                severity='medium',
                deskripsi=(
                    f"Transaksi bernilai besar: Rp {float(total):,.0f} "
                    f"(batas wajar: Rp {threshold:,.0f}). "
                    f"Tipe: {type(transaction).__name__} #{transaction.pk}. "
                    f"Diinput oleh: {user.get_full_name() or user.username if user else 'Unknown'}."
                ),
                user_terkait=user,
                nominal=total,
                model_name=type(transaction).__name__,
                object_id=str(transaction.pk),
            )
        return None
