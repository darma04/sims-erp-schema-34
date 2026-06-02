"""
==========================================================================
 PIUTANG (ACCOUNTS RECEIVABLE) - Modul Piutang Usaha
==========================================================================
 Modul ini mengelola:
 1. Piutang dari Sales Order (kredit/tempo)
 2. Piutang dari POS (kasbon)
 3. Pelunasan piutang (partial/full) dengan integrasi jurnal otomatis
 4. Aging Report piutang (0-30, 31-60, 61-90, >90 hari)

 Integrasi:
 - apps.penjualan.models → Customer, SalesOrder
 - apps.pos.models → POSTransaction, MetodePembayaran
 - apps.akuntansi.models → JurnalEntry (auto-jurnal pelunasan)
 - apps.produk.models → Gudang (dimensi cabang)
==========================================================================
"""

default_app_config = 'apps.piutang.apps.PiutangConfig'
