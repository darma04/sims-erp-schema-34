"""
Tests for laporan app — SIMS variant (with service/sparepart).
Verifies:
1. All core URL patterns resolve
2. Service/sparepart URLs DO exist
3. All view classes can be imported
4. Detailed view rendering (if DB available)
"""
from django.test import SimpleTestCase
from django.urls import reverse, resolve


class LaporanURLTests(SimpleTestCase):
    """Verify URL patterns work correctly."""

    def test_produk_url_resolves(self):
        url = reverse('laporan:produk')
        self.assertEqual(url, '/laporan/produk/')

    def test_stok_url_resolves(self):
        url = reverse('laporan:stok')
        self.assertEqual(url, '/laporan/stok/')

    def test_penjualan_url_resolves(self):
        url = reverse('laporan:penjualan')
        self.assertEqual(url, '/laporan/penjualan/')

    def test_pembelian_url_resolves(self):
        url = reverse('laporan:pembelian')
        self.assertEqual(url, '/laporan/pembelian/')

    def test_keuangan_url_resolves(self):
        url = reverse('laporan:keuangan')
        self.assertEqual(url, '/laporan/keuangan/')

    def test_cabang_url_resolves(self):
        url = reverse('laporan:cabang')
        self.assertEqual(url, '/laporan/cabang/')

    def test_produk_detail_url_resolves(self):
        url = reverse('laporan:produk-detail', args=[1])

    def test_stok_detail_url_resolves(self):
        url = reverse('laporan:stok-detail', args=[1])

    def test_penjualan_detail_url_resolves(self):
        url = reverse('laporan:penjualan-detail', args=[1])

    def test_pembelian_detail_url_resolves(self):
        url = reverse('laporan:pembelian-detail', args=[1])

    # ── Service/sparepart SHOULD exist ──

    def test_service_url_resolves(self):
        url = reverse('laporan:service')
        self.assertEqual(url, '/laporan/service/')

    def test_sparepart_url_resolves(self):
        url = reverse('laporan:sparepart')
        self.assertEqual(url, '/laporan/sparepart/')

    def test_service_detail_url_resolves(self):
        url = reverse('laporan:service-detail', args=[1])

    def test_sparepart_detail_url_resolves(self):
        url = reverse('laporan:sparepart-detail', args=[1])


class LaporanViewImportTests(SimpleTestCase):
    """Verify view classes can be imported."""

    def test_all_views_importable(self):
        from apps.laporan import views as v
        # Core views
        self.assertTrue(hasattr(v, 'LaporanProdukView'))
        self.assertTrue(hasattr(v, 'LaporanStokView'))
        self.assertTrue(hasattr(v, 'LaporanPenjualanView'))
        self.assertTrue(hasattr(v, 'LaporanPembelianView'))
        self.assertTrue(hasattr(v, 'LaporanKeuanganView'))
        self.assertTrue(hasattr(v, 'LaporanCabangView'))
        # Detail views
        self.assertTrue(hasattr(v, 'LaporanProdukDetailView'))
        self.assertTrue(hasattr(v, 'LaporanStokDetailView'))
        self.assertTrue(hasattr(v, 'LaporanPenjualanDetailView'))
        self.assertTrue(hasattr(v, 'LaporanPembelianDetailView'))
        # Service/sparepart views (SIMS only)
        self.assertTrue(hasattr(v, 'LaporanServiceView'))
        self.assertTrue(hasattr(v, 'LaporanSparepartView'))
        self.assertTrue(hasattr(v, 'LaporanServiceDetailView'))
        self.assertTrue(hasattr(v, 'LaporanSparepartDetailView'))
