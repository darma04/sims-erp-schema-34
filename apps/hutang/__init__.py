"""
==========================================================================
 HUTANG (ACCOUNTS PAYABLE) - Modul Hutang Usaha
==========================================================================
 Modul ini mengelola:
 1. Hutang dari Purchase Order (kredit/tempo)
 2. Pelunasan hutang (partial/full) dengan integrasi jurnal otomatis
 3. Aging Report hutang (0-30, 31-60, 61-90, >90 hari)

 Integrasi:
 - apps.pembelian.models → Supplier, PurchaseOrder
 - apps.pos.models → MetodePembayaran
 - apps.akuntansi.models → JurnalEntry (auto-jurnal pelunasan)
 - apps.produk.models → Gudang (dimensi cabang)
==========================================================================
"""

default_app_config = 'apps.hutang.apps.HutangConfig'
