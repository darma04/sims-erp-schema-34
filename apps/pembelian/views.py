"""
==========================================================================
 PEMBELIAN VIEWS - View CRUD untuk Supplier & Purchase Order (PO)
==========================================================================
 File ini berisi semua view untuk modul Pembelian:

 SUPPLIER CRUD:
   SupplierListView   → Daftar supplier
   SupplierCreateView → Tambah supplier baru
   SupplierUpdateView → Edit supplier
   SupplierDeleteView → Hapus supplier (JSON response)

 PURCHASE ORDER CRUD:
   PurchaseOrderListView   → Daftar PO + summary metrics
   PurchaseOrderCreateView → Buat PO baru + create produk baru otomatis
   PurchaseOrderDetailView → Detail PO + items
   PurchaseOrderPrintView  → Cetak PO (menggunakan TemplateCetak)
   PurchaseOrderUpdateView → Edit PO + items (formset)
   PurchaseOrderDeleteView → Hapus PO + rollback stok + hapus produk orphan

 FUNCTION-BASED:
   purchase_order_receive() → Terima barang + update stok

 FITUR UNIK PO CREATE:
 - Saat buat PO baru, produk baru OTOMATIS dibuat jika belum ada
 - SKU auto-generate (PRD-xxxxxxxxxx)
 - Harga jual = harga beli × 1.2 (markup 20%)
 - Stok langsung ditambahkan ke gudang tujuan
 - Status langsung 'received' (simplified workflow)
 - Notifikasi Telegram dikirim setelah PO dibuat
==========================================================================
"""

from django.shortcuts import render
from django.db.models import ProtectedError
from django.shortcuts import redirect, get_object_or_404
# Import dari framework Django
from django.contrib.auth.decorators import login_required
# Import dari framework Django
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView
# Import dari framework Django
from django.urls import reverse_lazy
# Import dari framework Django
from django.contrib import messages
# Import dari framework Django
from django.utils.decorators import method_decorator
# Import dari framework Django
from django.db import transaction  # Atomic transaction untuk operasi stok
from web_project import TemplateLayout
# Import dari modul internal proyek
from apps.pembelian.models import Supplier, PurchaseOrder, PurchaseOrderItem
# Import dari modul internal proyek
from apps.pembelian.forms import SupplierForm, PurchaseOrderForm
# Import dari modul internal proyek
from apps.core.mixins import ReadPermissionMixin, CreatePermissionMixin, UpdatePermissionMixin, DeletePermissionMixin


# ╔══════════════════════════════════════════════════════════════╗
# ║                   SUPPLIER CRUD                                ║
# ╚══════════════════════════════════════════════════════════════╝

class SupplierListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """Daftar semua supplier. URL: /pembelian/supplier/"""
    model = Supplier
    # Template HTML yang digunakan untuk render halaman
    template_name = 'pembelian/supplier_list.html'
    context_object_name = 'supplier_list'
    # Modul permission yang dicek: 'pembelian'
    permission_module = 'pembelian'
    permission_sub_module = 'supplier'
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: total_supplier — untuk ditampilkan di template
        context['total_supplier'] = self.get_queryset().count()
        return context


class SupplierCreateView(CreatePermissionMixin, CreateView):
    """Form tambah supplier baru. URL: /pembelian/supplier/add/"""
    model = Supplier
    form_class = SupplierForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'pembelian/supplier_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('pembelian:supplier')
    # Modul permission yang dicek: 'pembelian'
    permission_module = 'pembelian'
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title — untuk ditampilkan di template
        context['title'] = 'Tambah Supplier'
        return context
    
    def form_valid(self, form):
        """Dipanggil saat form valid — proses penyimpanan data."""
        messages.success(self.request, 'Supplier berhasil ditambahkan')
        return super().form_valid(form)


class SupplierUpdateView(UpdatePermissionMixin, UpdateView):
    """Form edit supplier. URL: /pembelian/supplier/<pk>/edit/"""
    model = Supplier
    form_class = SupplierForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'pembelian/supplier_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('pembelian:supplier')
    # Modul permission yang dicek: 'pembelian'
    permission_module = 'pembelian'
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title — untuk ditampilkan di template
        context['title'] = 'Edit Supplier'
        return context
    
    def form_valid(self, form):
        """Dipanggil saat form valid — proses penyimpanan data."""
        messages.success(self.request, 'Supplier berhasil diupdate')
        return super().form_valid(form)


class SupplierDeleteView(DeletePermissionMixin, DeleteView):
    """
    Hapus supplier — return JSON untuk AJAX.
    ⚠ Gagal jika supplier masih punya PO (FK PROTECT)
    """
    model = Supplier
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('pembelian:supplier')
    # Modul permission yang dicek: 'pembelian'
    permission_module = 'pembelian'
    
    def delete(self, request, *args, **kwargs):
        """Hapus data — return JSON response untuk AJAX."""
        from django.http import JsonResponse
        self.object = self.get_object()
        
        # Blok penanganan error — coba jalankan kode di bawah
        try:
            supplier_name = self.object.nama
            self.object.delete()
            return JsonResponse({
                'success': True, 
                'message': f'Supplier {supplier_name} berhasil dihapus'
            })
        # Tangkap error Exception — lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False, 
                'message': f'Gagal menghapus supplier: {str(e)}'
            }, status=400)


# ╔══════════════════════════════════════════════════════════════╗
# ║                PURCHASE ORDER CRUD                             ║
# ╚══════════════════════════════════════════════════════════════╝

class PurchaseOrderListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """
    Daftar semua Purchase Order + summary metrics.
    URL: /pembelian/purchase-order/
    Context tambahan: total_nominal_po, supplier_list (untuk filter)
    """
    model = PurchaseOrder
    # Template HTML yang digunakan untuk render halaman
    template_name = 'pembelian/purchase_order_list.html'
    context_object_name = 'purchase_order_list'
    # Modul permission yang dicek: 'pembelian'
    permission_module = 'pembelian'
    permission_sub_module = 'purchase_order'
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Import dari framework Django
        from django.db.models import Sum
        queryset = self.get_queryset()
        # Data konteks: total_purchase_order — untuk ditampilkan di template
        context['total_purchase_order'] = queryset.count()
        # Data konteks: total_nominal_po — untuk ditampilkan di template
        context['total_nominal_po'] = queryset.aggregate(Sum('total_harga'))['total_harga__sum'] or 0
        # Query database — ambil data context['supplier_list'] yang sesuai filter
        # Data konteks: supplier_list — untuk ditampilkan di template
        context['supplier_list'] = Supplier.objects.filter(aktif=True)
        return context


class PurchaseOrderCreateView(CreatePermissionMixin, CreateView):
    """
    Buat Purchase Order baru + OTOMATIS buat produk baru.
    URL: /pembelian/purchase-order/add/

    ALUR KHUSUS (berbeda dari CRUD biasa):
    1. User input nama produk, jumlah, harga di form
    2. Untuk setiap item:
       a. Buat record Produk baru (SKU auto-generate, markup 20%)
       b. Buat PurchaseOrderItem
       c. Langsung update stok di gudang tujuan
    3. PO langsung set status 'received'
    4. Kirim notifikasi Telegram
    5. Log ke activity_log
    """
    model = PurchaseOrder
    form_class = PurchaseOrderForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'pembelian/purchase_order_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('pembelian:purchase-order')
    # Modul permission yang dicek: 'pembelian'
    permission_module = 'pembelian'
    permission_sub_module = 'purchase_order'
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title — untuk ditampilkan di template
        context['title'] = 'Buat Purchase Order Baru'
        # Sediakan data kategori dan satuan untuk dropdown di template
        from apps.produk.models import Kategori, Satuan
        # Query database — ambil semua data context['kategori_list']
        # Data konteks: kategori_list — untuk ditampilkan di template
        context['kategori_list'] = Kategori.objects.all()
        # Query database — ambil semua data context['satuan_list']
        # Data konteks: satuan_list — untuk ditampilkan di template
        context['satuan_list'] = Satuan.objects.all()
        # Data konteks: tipe_choices — untuk dropdown tipe Produk/Sparepart
        from apps.produk.models import Produk
        context['tipe_choices'] = Produk.TIPE_CHOICES
        return context
    
    def form_valid(self, form):
        """
        Override form_valid untuk proses kustom pembuatan PO.
        Items diambil dari POST data manual (bukan formset standar).
        """
        from apps.produk.models import Produk, Kategori, Satuan
        from decimal import Decimal
        import random
        
        # DIPERBAIKI QA-P1: Seluruh proses dalam atomic transaction
        # agar tidak ada produk/stok orphan jika error di tengah loop
        with transaction.atomic():
            # Simpan PO (tanpa items dulu)
            po = form.save(commit=False)
            po.dibuat_oleh = self.request.user
            
            if not po.nomor_po:
                po.nomor_po = po.generate_nomor()
            
            po.save()
                
            # Proses setiap item dari POST data
            items_created = 0
            i = 0
            while True:
                nama_produk = self.request.POST.get(f'items-{i}-nama_produk')
                if nama_produk is None:
                    break
                    
                # Skip baris kosong
                if not nama_produk.strip():
                    i += 1
                    continue
                    
                jumlah = self.request.POST.get(f'items-{i}-jumlah', '0')
                harga_satuan = self.request.POST.get(f'items-{i}-harga_satuan', '0')
                kategori_id = self.request.POST.get(f'items-{i}-kategori')
                satuan_id = self.request.POST.get(f'items-{i}-satuan')
                catatan = self.request.POST.get(f'items-{i}-catatan', '')
                tipe_item = self.request.POST.get(f'items-{i}-tipe', 'produk')  # Tipe: produk atau sparepart
                    
                # Blok penanganan error — coba jalankan kode di bawah
                try:
                    jumlah = Decimal(jumlah) if jumlah else Decimal('0')
                    harga_satuan = Decimal(harga_satuan) if harga_satuan else Decimal('0')
                except (ValueError, InvalidOperation):
                    i += 1
                    continue
                    
                if jumlah <= 0 or harga_satuan <= 0:
                    i += 1
                    continue
                    
                # Dapatkan kategori dan satuan (fallback ke yang pertama jika tidak valid)
                kategori = None
                satuan = None
                    
                if kategori_id:
                    try:
                        kategori = Kategori.objects.get(pk=kategori_id)
                    except Kategori.DoesNotExist:
                        pass
                if not kategori:
                    kategori = Kategori.objects.first()
                    
                if satuan_id:
                    try:
                        satuan = Satuan.objects.get(pk=satuan_id)
                    except Satuan.DoesNotExist:
                        pass
                if not satuan:
                    satuan = Satuan.objects.first()
                    
                # Generate SKU unik berdasarkan tipe (SPR untuk sparepart, PRD untuk produk)
                sku_prefix = 'SPR' if tipe_item == 'sparepart' else 'PRD'
                sku = f"{sku_prefix}-{random.randint(1000000000, 9999999999)}"
                while Produk.objects.filter(sku=sku).exists():
                    sku = f"{sku_prefix}-{random.randint(1000000000, 9999999999)}"
                    
                # Buat Produk baru
                produk = Produk.objects.create(
                    sku=sku,
                    nama=nama_produk.strip(),
                    kategori=kategori,
                    satuan=satuan,
                    harga_beli=harga_satuan,
                    harga_jual=harga_satuan * Decimal('1.2'),  # Markup 20%
                    tipe=tipe_item,  # Tipe: produk atau sparepart
                    aktif=True,
                    dibuat_oleh=self.request.user
                )
                    
                # Buat PurchaseOrderItem
                PurchaseOrderItem.objects.create(
                    purchase_order=po,
                    produk=produk,
                    jumlah=jumlah,
                    harga_satuan=harga_satuan,
                    catatan=catatan
                )
                    
                # Update stok langsung di gudang tujuan (dengan lock)
                from apps.produk.models import Stok
                stok, created = Stok.objects.select_for_update().get_or_create(
                    produk=produk,
                    gudang=po.gudang,
                    defaults={'jumlah': 0}
                )
                stok.jumlah += jumlah
                stok.save()

                # Update cabang produk ke gudang dengan stok terbanyak
                stok_terbanyak = Stok.objects.filter(
                    produk=produk, jumlah__gt=0
                ).order_by('-jumlah').first()

                if stok_terbanyak:
                    if produk.cabang != stok_terbanyak.gudang:
                        produk.cabang = stok_terbanyak.gudang
                        produk.save(update_fields=['cabang'])
                    
                items_created += 1
                i += 1
                
            # Set status langsung ke received
            po.status = 'received'
            po.calculate_total()
            po.save()
        
        # Notifikasi dan log di luar atomic (opsional, tidak boleh rollback PO)
        try:
            from apps.automation.signals import kirim_notifikasi_purchase_order
            kirim_notifikasi_purchase_order(po)
        except Exception:
            pass
        
        # Log activity
        from apps.activity_log.middleware import ActivityLogMiddleware
        ActivityLogMiddleware.log_activity(
            self.request,
            action='create',
            model_name='Purchase Order',
            object_id=po.pk,
            object_repr=str(po),
            description=f'Membuat Purchase Order: {po.nomor_po} ke {po.supplier.nama} ({items_created} produk baru)'
        )
        
        # Tampilkan pesan sukses ke user
        messages.success(self.request, f'Purchase Order {po.nomor_po} berhasil dibuat dengan {items_created} produk baru')
        # Redirect ke halaman tujuan
        return redirect(self.success_url)


class PurchaseOrderDetailView(ReadPermissionMixin, TemplateView):
    """Detail PO + items. URL: /pembelian/purchase-order/<pk>/"""
    template_name = 'pembelian/purchase_order_detail.html'
    # Modul permission yang dicek: 'pembelian'
    permission_module = 'pembelian'
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        po_id = kwargs.get('pk')
        # Data konteks: purchase_order — untuk ditampilkan di template
        context['purchase_order'] = get_object_or_404(PurchaseOrder, pk=po_id)
        return context


class PurchaseOrderPrintView(ReadPermissionMixin, TemplateView):
    """
    Cetak PO — menggunakan TemplateCetak untuk format.
    URL: /pembelian/purchase-order/<pk>/print/
    Template cetak diambil dari apps/pengaturan/models.TemplateCetak
    """
    template_name = 'pembelian/purchase_order_print.html'
    # Modul permission yang dicek: 'pembelian'
    permission_module = 'pembelian'
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = super().get_context_data(**kwargs)
        po_id = kwargs.get('pk')
        # Data konteks: purchase_order — untuk ditampilkan di template
        context['purchase_order'] = get_object_or_404(PurchaseOrder, pk=po_id)
        # Import dari modul internal proyek
        from apps.pengaturan.models import TemplateCetak, PengaturanPerusahaan
        # Data konteks: template — untuk ditampilkan di template
        context['template'] = TemplateCetak.get_template('purchase_order')
        # Data konteks: perusahaan — untuk logo di header cetak
        context['perusahaan'] = PengaturanPerusahaan.load()
        return context


class PurchaseOrderUpdateView(UpdatePermissionMixin, UpdateView):
    """
    Edit PO + items menggunakan formset.
    URL: /pembelian/purchase-order/<pk>/edit/
    Setelah save: recalculate total + log activity
    """
    model = PurchaseOrder
    form_class = PurchaseOrderForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'pembelian/purchase_order_edit.html'
    # Modul permission yang dicek: 'pembelian'
    permission_module = 'pembelian'
    permission_sub_module = 'purchase_order'
    
    def get_success_url(self):
        """URL redirect setelah operasi berhasil."""
        return reverse_lazy('pembelian:purchase-order-detail', kwargs={'pk': self.object.pk})
    
    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title — untuk ditampilkan di template
        context['title'] = 'Edit Purchase Order'
        
        # Import dari modul internal proyek
        from apps.pembelian.forms import PurchaseOrderItemFormSet
        # Import dari modul internal proyek
        from apps.produk.models import Produk
        
        # Sediakan formset dengan data existing
        if self.request.POST:
            # Data konteks: formset — untuk ditampilkan di template
            context['formset'] = PurchaseOrderItemFormSet(self.request.POST, instance=self.object)
        else:
            # Data konteks: formset — untuk ditampilkan di template
            context['formset'] = PurchaseOrderItemFormSet(instance=self.object)
        
        # Query database — ambil data context['produk_list'] yang sesuai filter
        # Data konteks: produk_list — untuk ditampilkan di template
        context['produk_list'] = Produk.objects.filter(aktif=True)
        return context
    
    def form_valid(self, form):
        """Dipanggil saat form valid — proses penyimpanan data."""
        context = self.get_context_data()
        # Data konteks: formset — untuk ditampilkan di template
        formset = context['formset']
        
        if formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            formset.save()
            
            # Recalculate total setelah items berubah
            self.object.calculate_total()
            self.object.save()
            
            # Log activity
            from apps.activity_log.middleware import ActivityLogMiddleware
            ActivityLogMiddleware.log_activity(
                self.request,
                action='update',
                model_name='Purchase Order',
                object_id=self.object.pk,
                object_repr=str(self.object),
                description=f'Mengubah Purchase Order: {self.object.nomor_po} - Rp {self.object.total_harga:,.0f}'
            )
            
            # Tampilkan pesan sukses ke user
            messages.success(self.request, 'Purchase Order berhasil diupdate')
            # Redirect ke halaman tujuan
            return redirect(self.get_success_url())
        else:
            return self.render_to_response(self.get_context_data(form=form))


class PurchaseOrderDeleteView(DeletePermissionMixin, DeleteView):
    """
    Hapus PO — rollback stok + hapus produk orphan.
    URL: /pembelian/purchase-order/<pk>/delete/

    ALUR PENGHAPUSAN:
    1. Log activity (sebelum hapus agar masih ada data)
    2. Untuk setiap item PO:
       a. Rollback stok (kurangi jumlah dari gudang)
       b. Cek apakah produk hanya referensi dari PO ini
       c. Jika produk orphan (tidak ada di SO, POS, transfer) → hapus produk
    3. Hapus PO (items CASCADE otomatis)
    """
    model = PurchaseOrder
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('pembelian:purchase-order')
    # Modul permission yang dicek: 'pembelian'
    permission_module = 'pembelian'
    permission_sub_module = 'purchase_order'
    
    def post(self, request, *args, **kwargs):
        """Override post() agar memanggil delete() yang return JSON."""
        return self.delete(request, *args, **kwargs)
    
    def delete(self, request, *args, **kwargs):
        """Hapus data — return JSON response untuk AJAX."""
        from django.http import JsonResponse
        # Import dari modul internal proyek
        from apps.produk.models import Stok
        from apps.fraud_detection.signals import set_current_delete_user, clear_current_delete_user
        
        self.object = self.get_object()
        po = self.object
        
        # Log activity sebelum hapus (agar referensi masih ada)
        from apps.activity_log.middleware import ActivityLogMiddleware
        ActivityLogMiddleware.log_activity(
            request,
            action='delete',
            model_name='Purchase Order',
            object_id=po.pk,
            object_repr=str(po),
            description=f'Menghapus Purchase Order: {po.nomor_po}'
        )
        
        # Seluruh proses rollback + hapus dalam atomic transaction
        try:
            # 1. Kumpulkan produk orphan SEBELUM hapus PO
            orphan_products = []
            for item in po.items.all():
                # Rollback stok (dengan lock untuk mencegah race condition)
                try:
                    stok = Stok.objects.select_for_update().get(
                        produk=item.produk, gudang=po.gudang
                    )
                    stok.jumlah -= item.jumlah
                    if stok.jumlah < 0:
                        stok.jumlah = 0  # Pastikan tidak negatif
                    stok.save()

                    # Update cabang produk ke gudang dengan stok terbanyak
                    stok_terbanyak = Stok.objects.filter(
                        produk=item.produk, jumlah__gt=0
                    ).order_by('-jumlah').first()

                    if stok_terbanyak:
                        if item.produk.cabang != stok_terbanyak.gudang:
                            item.produk.cabang = stok_terbanyak.gudang
                            item.produk.save(update_fields=['cabang'])
                except Stok.DoesNotExist:
                    pass
                    
                # Tandai produk orphan (hanya ada di PO ini, tidak ada di modul lain)
                if item.produk.purchaseorderitem_set.count() == 1:
                    if not item.produk.salesorderitem_set.exists() and \
                       not item.produk.postransactionitem_set.exists() and \
                       not item.produk.transferstokitem_set.exists():
                        orphan_products.append(item.produk.pk)
                
            # 2. Hapus PO dulu (items CASCADE otomatis → FK ke produk terlepas)
            set_current_delete_user(request.user)
            po.delete()
            clear_current_delete_user()
            
            # 3. Hapus produk orphan SETELAH PO & items sudah dihapus
            from apps.produk.models import Produk
            if orphan_products:
                Produk.objects.filter(pk__in=orphan_products).delete()
            
            return JsonResponse({'success': True, 'message': 'Purchase Order berhasil dihapus'})
        except ProtectedError:
            clear_current_delete_user()
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            clear_current_delete_user()
            return JsonResponse({'success': False, 'message': str(e)}, status=400)


# ╔══════════════════════════════════════════════════════════════╗
# ║           FUNCTION-BASED VIEW: RECEIVE GOODS                   ║
# ╚══════════════════════════════════════════════════════════════╝

# Wajib login — redirect ke login page jika belum login
@login_required
def purchase_order_receive(request, pk):
    """
    Terima barang dari supplier — update stok di gudang.
    URL: /pembelian/purchase-order/<pk>/receive/

    Alur:
    1. Cek apakah PO sudah diterima → error jika ya
    2. Auto-approve jika status masih draft
    3. Panggil po.receive_goods() → tambah stok per item
    4. Log activity
    """
    po = get_object_or_404(PurchaseOrder, pk=pk)
    
    if po.status == 'received':
        # Tampilkan pesan error ke user
        messages.error(request, 'PO ini sudah diterima sebelumnya')
        # Redirect ke halaman tujuan
        return redirect('pembelian:purchase-order-detail', pk=pk)
    
    # Blok penanganan error — coba jalankan kode di bawah
    try:
        # Auto-approve jika masih draft
        if po.status == 'draft':
            po.status = 'approved'
            po.save()
        
        # Receive goods → update stok (lihat PurchaseOrder.receive_goods())
        po.receive_goods(request.user)
        
        # Log activity
        from apps.activity_log.middleware import ActivityLogMiddleware
        ActivityLogMiddleware.log_activity(
            request,
            action='update',
            model_name='Purchase Order',
            object_id=po.pk,
            object_repr=str(po),
            description=f'Menerima barang untuk PO: {po.nomor_po} - stok diupdate'
        )
        
        # Tampilkan pesan sukses ke user
        messages.success(request, f'Barang untuk PO {po.nomor_po} berhasil diterima dan stok diupdate')
    # Tangkap error ValueError — lanjutkan tanpa crash
    except ValueError as e:
        # Tampilkan pesan error ke user
        messages.error(request, str(e))
    # Tangkap error Exception — lanjutkan tanpa crash
    except ProtectedError:
        return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
    except Exception as e:
        # Tampilkan pesan error ke user
        messages.error(request, f'Terjadi kesalahan: {str(e)}')
    
    # Redirect ke halaman tujuan
    return redirect('pembelian:purchase-order-detail', pk=pk)
