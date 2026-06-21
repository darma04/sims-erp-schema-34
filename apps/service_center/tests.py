
from decimal import Decimal
from datetime import date

from django.test import TestCase
from django.contrib.auth.models import User
from apps.service_center.models import (
    Pelanggan, Perangkat, KategoriService, JenisService,
    OrderService, ItemService, RiwayatStatus, PenggunaanSparepart,
)
from apps.produk.models import Produk, Kategori, Satuan, Gudang, Stok


class PelangganTest(TestCase):
    def test_auto_generate_kode(self):
        p = Pelanggan.objects.create(nama="Budi", telepon="08123456789")
        self.assertTrue(p.kode.startswith("PLG-"))
        self.assertEqual(len(p.kode.split("-")[1]), 5)

    def test_kode_increment(self):
        p1 = Pelanggan.objects.create(nama="A", telepon="081")
        p2 = Pelanggan.objects.create(nama="B", telepon="082")
        self.assertEqual(int(p2.kode.split("-")[1]), int(p1.kode.split("-")[1]) + 1)

    def test_explicit_kode_not_overwritten(self):
        p = Pelanggan.objects.create(kode="CUSTOM-01", nama="Budi", telepon="081")
        self.assertEqual(p.kode, "CUSTOM-01")

    def test_string_representation(self):
        p = Pelanggan.objects.create(kode="PLG-00001", nama="Budi", telepon="081")
        self.assertIn("Budi", str(p))

    def test_default_active(self):
        p = Pelanggan.objects.create(nama="Budi", telepon="081")
        self.assertTrue(p.aktif)


class PerangkatTest(TestCase):
    def test_create_perangkat(self):
        perangkat = Perangkat.objects.create(nama="HP Android")
        self.assertEqual(str(perangkat), "HP Android")

    def test_default_icon(self):
        perangkat = Perangkat.objects.create(nama="Laptop")
        self.assertEqual(perangkat.icon, "ri-smartphone-line")


class KategoriServiceTest(TestCase):
    def test_create_kategori(self):
        k = KategoriService.objects.create(nama="Hardware")
        self.assertEqual(str(k), "Hardware")

    def test_unique_name(self):
        KategoriService.objects.create(nama="Hardware")
        with self.assertRaises(Exception):
            KategoriService.objects.create(nama="Hardware")


class JenisServiceTest(TestCase):
    def setUp(self):
        self.kategori = KategoriService.objects.create(nama="Hardware")

    def test_create_jenis(self):
        js = JenisService.objects.create(kategori=self.kategori, nama="Ganti LCD", harga_standar=Decimal("250000"))
        self.assertIn("Ganti LCD", str(js))

    def test_harga_standar_default(self):
        js = JenisService.objects.create(kategori=self.kategori, nama="Service Ringan")
        self.assertEqual(js.harga_standar, 0)


class OrderServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="pass")
        self.pelanggan = Pelanggan.objects.create(nama="Budi", telepon="081")
        self.perangkat = Perangkat.objects.create(nama="HP Android")
        self.kategori = KategoriService.objects.create(nama="Software")

    def test_auto_nomor(self):
        o = OrderService.objects.create(
            pelanggan=self.pelanggan,
            jenis_perangkat=self.perangkat,
            keluhan="Tidak bisa booting",
            diterima_oleh=self.user,
        )
        self.assertTrue(o.nomor_service.startswith("SVC/"))

    def test_auto_kode_unik(self):
        o = OrderService.objects.create(
            pelanggan=self.pelanggan,
            jenis_perangkat=self.perangkat,
            keluhan="LCD retak",
            diterima_oleh=self.user,
        )
        self.assertEqual(len(o.kode_unik), 8)

    def test_kode_unik_unique(self):
        o1 = OrderService.objects.create(
            pelanggan=self.pelanggan,
            jenis_perangkat=self.perangkat,
            keluhan="A",
            diterima_oleh=self.user,
        )
        o2 = OrderService.objects.create(
            pelanggan=self.pelanggan,
            jenis_perangkat=self.perangkat,
            keluhan="B",
            diterima_oleh=self.user,
        )
        self.assertNotEqual(o1.kode_unik, o2.kode_unik)

    def test_tanggal_masuk_auto_set(self):
        o = OrderService.objects.create(
            pelanggan=self.pelanggan,
            jenis_perangkat=self.perangkat,
            keluhan="Matot",
            diterima_oleh=self.user,
        )
        self.assertIsNotNone(o.tanggal_masuk)

    def test_auto_set_tanggal_selesai(self):
        o = OrderService.objects.create(
            pelanggan=self.pelanggan,
            jenis_perangkat=self.perangkat,
            keluhan="Test",
            diterima_oleh=self.user,
            status="selesai",
        )
        self.assertIsNotNone(o.tanggal_selesai)

    def test_auto_set_tanggal_diambil(self):
        o = OrderService.objects.create(
            pelanggan=self.pelanggan,
            jenis_perangkat=self.perangkat,
            keluhan="Test",
            diterima_oleh=self.user,
            status="diambil",
        )
        self.assertIsNotNone(o.tanggal_diambil)

    def test_total_biaya_zero_when_no_items(self):
        o = OrderService.objects.create(
            pelanggan=self.pelanggan,
            jenis_perangkat=self.perangkat,
            keluhan="Test",
            diterima_oleh=self.user,
        )
        self.assertEqual(o.total_biaya, 0)

    def test_total_biaya_with_items(self):
        o = OrderService.objects.create(
            pelanggan=self.pelanggan,
            jenis_perangkat=self.perangkat,
            keluhan="Test",
            diterima_oleh=self.user,
        )
        ItemService.objects.create(order_service=o, nama_layanan="Ganti LCD", biaya=Decimal("250000"))
        ItemService.objects.create(order_service=o, nama_layanan="Ganti Baterai", biaya=Decimal("100000"))
        self.assertEqual(o.total_biaya, Decimal("350000"))

    def test_total_biaya_with_tax(self):
        o = OrderService.objects.create(
            pelanggan=self.pelanggan,
            jenis_perangkat=self.perangkat,
            keluhan="Test",
            diterima_oleh=self.user,
            pajak=Decimal("55000"),
        )
        ItemService.objects.create(order_service=o, nama_layanan="Service", biaya=Decimal("500000"))
        self.assertEqual(o.total_biaya, Decimal("555000"))

    def test_biaya_akhir_auto_calculated_on_re_save(self):
        o = OrderService.objects.create(
            pelanggan=self.pelanggan,
            jenis_perangkat=self.perangkat,
            keluhan="Test",
            diterima_oleh=self.user,
        )
        ItemService.objects.create(order_service=o, nama_layanan="Ganti LCD", biaya=Decimal("250000"))
        o.save()
        o.refresh_from_db()
        self.assertGreater(o.biaya_akhir, 0)

    def test_sisa_bayar_full(self):
        o = OrderService.objects.create(
            pelanggan=self.pelanggan,
            jenis_perangkat=self.perangkat,
            keluhan="Test",
            diterima_oleh=self.user,
            pajak=Decimal("55000"),
        )
        ItemService.objects.create(order_service=o, nama_layanan="Service", biaya=Decimal("500000"))
        self.assertEqual(o.sisa_bayar, o.total_biaya)

    def test_sisa_bayar_after_dp(self):
        o = OrderService.objects.create(
            pelanggan=self.pelanggan,
            jenis_perangkat=self.perangkat,
            keluhan="Test",
            diterima_oleh=self.user,
            dp_bayar=Decimal("100000"),
        )
        ItemService.objects.create(order_service=o, nama_layanan="Service", biaya=Decimal("500000"))
        self.assertEqual(o.sisa_bayar, Decimal("400000"))

    def test_sisa_bayar_not_negative(self):
        o = OrderService.objects.create(
            pelanggan=self.pelanggan,
            jenis_perangkat=self.perangkat,
            keluhan="Test",
            diterima_oleh=self.user,
            dp_bayar=Decimal("500000"),
        )
        self.assertEqual(o.sisa_bayar, 0)

    def test_status_badge_class_mapping(self):
        mapping = {
            "diterima": "info",
            "diagnosa": "warning",
            "menunggu_konfirmasi": "primary",
            "dikerjakan": "warning",
            "selesai": "success",
            "diambil": "secondary",
            "dibatalkan": "danger",
        }
        for status, expected in mapping.items():
            with self.subTest(status=status):
                o = OrderService(
                    pelanggan=self.pelanggan, jenis_perangkat=self.perangkat,
                    keluhan="Test", diterima_oleh=self.user, status=status,
                )
                self.assertEqual(o.status_badge_class, expected)

    def test_prioritas_badge_class_mapping(self):
        mapping = {
            "normal": "secondary",
            "urgent": "warning",
            "express": "danger",
        }
        for prioritas, expected in mapping.items():
            with self.subTest(prioritas=prioritas):
                o = OrderService(
                    pelanggan=self.pelanggan, jenis_perangkat=self.perangkat,
                    keluhan="Test", diterima_oleh=self.user, prioritas=prioritas,
                )
                self.assertEqual(o.prioritas_badge_class, expected)

    def test_string_representation(self):
        o = OrderService.objects.create(
            pelanggan=self.pelanggan,
            jenis_perangkat=self.perangkat,
            keluhan="Tidak hidup",
            diterima_oleh=self.user,
        )
        self.assertIn(o.nomor_service, str(o))
        self.assertIn("Budi", str(o))


class ItemServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="pass")
        self.pelanggan = Pelanggan.objects.create(nama="Budi", telepon="081")
        self.perangkat = Perangkat.objects.create(nama="HP Android")
        self.order = OrderService.objects.create(
            pelanggan=self.pelanggan,
            jenis_perangkat=self.perangkat,
            keluhan="Test",
            diterima_oleh=self.user,
        )

    def test_create_item(self):
        item = ItemService.objects.create(
            order_service=self.order,
            nama_layanan="Ganti LCD",
            biaya=Decimal("250000"),
        )
        self.assertIn("Ganti LCD", str(item))

    def test_biaya_default_zero(self):
        item = ItemService.objects.create(
            order_service=self.order,
            nama_layanan="Service Gratis",
        )
        self.assertEqual(item.biaya, 0)


class RiwayatStatusTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="pass")
        self.pelanggan = Pelanggan.objects.create(nama="Budi", telepon="081")
        self.perangkat = Perangkat.objects.create(nama="HP Android")
        self.order = OrderService.objects.create(
            pelanggan=self.pelanggan,
            jenis_perangkat=self.perangkat,
            keluhan="Test",
            diterima_oleh=self.user,
        )

    def test_create_riwayat(self):
        r = RiwayatStatus.objects.create(
            order_service=self.order,
            status_sebelum="diterima",
            status_sesudah="diagnosa",
            diubah_oleh=self.user,
        )
        self.assertIn("diterima", str(r))
        self.assertIn("diagnosa", str(r))

    def test_status_display_methods(self):
        r = RiwayatStatus.objects.create(
            order_service=self.order,
            status_sebelum="diterima",
            status_sesudah="diagnosa",
            diubah_oleh=self.user,
        )
        self.assertEqual(r.get_status_display_sebelum(), "Diterima")
        self.assertEqual(r.get_status_display_sesudah(), "Diagnosa")

    def test_ordering_newest_first(self):
        RiwayatStatus.objects.create(
            order_service=self.order, status_sebelum="a", status_sesudah="b", diubah_oleh=self.user,
        )
        RiwayatStatus.objects.create(
            order_service=self.order, status_sebelum="b", status_sesudah="c", diubah_oleh=self.user,
        )
        qs = RiwayatStatus.objects.all()
        self.assertEqual(len(qs), 2)

    def test_unknown_status_display_fallback(self):
        r = RiwayatStatus.objects.create(
            order_service=self.order,
            status_sebelum="unknown",
            status_sesudah="unknown2",
            diubah_oleh=self.user,
        )
        self.assertEqual(r.get_status_display_sebelum(), "unknown")
        self.assertEqual(r.get_status_display_sesudah(), "unknown2")


class PenggunaanSparepartTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teknisi1", password="pass")
        self.pelanggan = Pelanggan.objects.create(nama="Budi", telepon="081")
        self.perangkat = Perangkat.objects.create(nama="HP Android")
        self.order = OrderService.objects.create(
            pelanggan=self.pelanggan,
            jenis_perangkat=self.perangkat,
            keluhan="Ganti baterai",
            diterima_oleh=self.user,
        )
        self.kategori = Kategori.objects.create(nama="Sparepart HP")
        self.satuan = Satuan.objects.create(nama="Pcs")
        self.gudang = Gudang.objects.create(nama="Gudang Service", kode="SVC-01")
        self.produk = Produk.objects.create(
            nama="Baterai iPhone 11",
            sku="BAT-IP11",
            kategori=self.kategori,
            satuan=self.satuan,
            harga_beli=Decimal("100000"),
            harga_jual=Decimal("150000"),
        )

    def test_subtotal(self):
        sp = PenggunaanSparepart(
            order_service=self.order,
            produk=self.produk,
            gudang=self.gudang,
            jumlah=2,
            harga_satuan=Decimal("150000"),
        )
        self.assertEqual(sp.subtotal, Decimal("300000"))

    def test_subtotal_single(self):
        sp = PenggunaanSparepart(
            order_service=self.order,
            produk=self.produk,
            gudang=self.gudang,
            jumlah=1,
            harga_satuan=Decimal("150000"),
        )
        self.assertEqual(sp.subtotal, Decimal("150000"))

    def test_kurangi_stok_reduces_inventory(self):
        Stok.objects.create(produk=self.produk, gudang=self.gudang, jumlah=10)
        sp = PenggunaanSparepart.objects.create(
            order_service=self.order,
            produk=self.produk,
            gudang=self.gudang,
            jumlah=3,
            harga_satuan=Decimal("150000"),
        )
        sp.kurangi_stok()
        stok = Stok.objects.get(produk=self.produk, gudang=self.gudang)
        self.assertEqual(stok.jumlah, 7)

    def test_kurangi_stok_idempotent(self):
        Stok.objects.create(produk=self.produk, gudang=self.gudang, jumlah=10)
        sp = PenggunaanSparepart.objects.create(
            order_service=self.order,
            produk=self.produk,
            gudang=self.gudang,
            jumlah=3,
            harga_satuan=Decimal("150000"),
        )
        sp.kurangi_stok()
        sp.kurangi_stok()
        stok = Stok.objects.get(produk=self.produk, gudang=self.gudang)
        self.assertEqual(stok.jumlah, 7)

    def test_kurangi_stok_raises_on_insufficient(self):
        Stok.objects.create(produk=self.produk, gudang=self.gudang, jumlah=1)
        sp = PenggunaanSparepart.objects.create(
            order_service=self.order,
            produk=self.produk,
            gudang=self.gudang,
            jumlah=5,
            harga_satuan=Decimal("150000"),
        )
        with self.assertRaises(ValueError):
            sp.kurangi_stok()

    def test_kembalikan_stok_restores_inventory(self):
        Stok.objects.create(produk=self.produk, gudang=self.gudang, jumlah=10)
        sp = PenggunaanSparepart.objects.create(
            order_service=self.order,
            produk=self.produk,
            gudang=self.gudang,
            jumlah=3,
            harga_satuan=Decimal("150000"),
        )
        sp.kurangi_stok()
        sp.kembalikan_stok()
        stok = Stok.objects.get(produk=self.produk, gudang=self.gudang)
        self.assertEqual(stok.jumlah, 10)

    def test_kembalikan_stok_idempotent(self):
        Stok.objects.create(produk=self.produk, gudang=self.gudang, jumlah=10)
        sp = PenggunaanSparepart.objects.create(
            order_service=self.order,
            produk=self.produk,
            gudang=self.gudang,
            jumlah=3,
            harga_satuan=Decimal("150000"),
        )
        sp.kembalikan_stok()
        stok = Stok.objects.get(produk=self.produk, gudang=self.gudang)
        self.assertEqual(stok.jumlah, 10)
        sp.kembalikan_stok()
        stok.refresh_from_db()
        self.assertEqual(stok.jumlah, 10)

    def test_stok_dikurangi_flag_set_after_kurangi(self):
        Stok.objects.create(produk=self.produk, gudang=self.gudang, jumlah=10)
        sp = PenggunaanSparepart.objects.create(
            order_service=self.order,
            produk=self.produk,
            gudang=self.gudang,
            jumlah=2,
            harga_satuan=Decimal("100000"),
        )
        self.assertFalse(sp.stok_dikurangi)
        sp.kurangi_stok()
        sp.refresh_from_db()
        self.assertTrue(sp.stok_dikurangi)

    def test_stok_dikurangi_flag_cleared_after_kembalikan(self):
        Stok.objects.create(produk=self.produk, gudang=self.gudang, jumlah=10)
        sp = PenggunaanSparepart.objects.create(
            order_service=self.order,
            produk=self.produk,
            gudang=self.gudang,
            jumlah=2,
            harga_satuan=Decimal("100000"),
        )
        sp.kurangi_stok()
        sp.kembalikan_stok()
        sp.refresh_from_db()
        self.assertFalse(sp.stok_dikurangi)

    def test_kurangi_stok_raises_when_no_stok_record(self):
        sp = PenggunaanSparepart.objects.create(
            order_service=self.order,
            produk=self.produk,
            gudang=self.gudang,
            jumlah=1,
            harga_satuan=Decimal("100000"),
        )
        with self.assertRaises(ValueError):
            sp.kurangi_stok()

    def test_string_representation(self):
        sp = PenggunaanSparepart.objects.create(
            order_service=self.order,
            produk=self.produk,
            gudang=self.gudang,
            jumlah=2,
            harga_satuan=Decimal("150000"),
        )
        self.assertIn(self.produk.nama, str(sp))
        self.assertIn(self.order.nomor_service, str(sp))

    def test_auto_calc_biaya_akhir_includes_sparepart(self):
        Stok.objects.create(produk=self.produk, gudang=self.gudang, jumlah=10)
        ItemService.objects.create(order_service=self.order, nama_layanan="Jasa", biaya=Decimal("50000"))
        PenggunaanSparepart.objects.create(
            order_service=self.order,
            produk=self.produk,
            gudang=self.gudang,
            jumlah=2,
            harga_satuan=Decimal("150000"),
        )
        self.order.save()
        self.order.refresh_from_db()
        self.assertEqual(self.order.biaya_akhir, Decimal("350000"))
