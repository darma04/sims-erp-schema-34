"""
==========================================================================
 AKUNTANSI APP - Modul Inti Akuntansi (Core Accounting Engine)
==========================================================================
 Package ini adalah jantung sistem akuntansi ERP.

 Berisi:
 - models.py → Akun (CoA), JurnalEntry, JurnalLine, PeriodeAkuntansi
 - views.py  → CRUD CoA, Jurnal, Buku Besar, Periode
 - forms.py  → Form Django untuk input data akuntansi
 - urls.py   → Routing URL modul akuntansi
 - services.py → Service layer untuk jurnal otomatis

 Terhubung dengan:
 - apps/pos/ → Trigger jurnal dari transaksi POS
 - apps/penjualan/ → Trigger jurnal dari Sales Order
 - apps/pembelian/ → Trigger jurnal dari Purchase Order
 - apps/biaya/ → Trigger jurnal dari biaya operasional
 - apps/hr/ → Trigger jurnal dari penggajian
 - apps/inventory/ → Trigger jurnal dari adjustment stok
 - apps/laporan/ → Data untuk laporan keuangan
 - apps/produk/ → Gudang sebagai dimensi cabang
==========================================================================
"""
