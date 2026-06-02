"""
==========================================================================
 ASET TETAP (FIXED ASSETS) - Modul Manajemen Aset Tetap
==========================================================================
 Modul ini mengelola:
 1. Registrasi aset tetap (peralatan, kendaraan, bangunan)
 2. Pembelian aset (tunai/kredit/DP+cicilan)
 3. Penyusutan otomatis (garis lurus / saldo menurun)
 4. Disposal aset (penjualan/penghapusan aset)

 Integrasi:
 - apps.akuntansi.models → Akun CoA, JurnalEntry (auto-jurnal)
 - apps.pembelian.models → Supplier
 - apps.pos.models → MetodePembayaran
 - apps.produk.models → Gudang (dimensi cabang)
==========================================================================
"""

default_app_config = 'apps.aset.apps.AsetConfig'
