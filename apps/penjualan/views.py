"""
==========================================================================
PENJUALAN VIEWS - View CRUD untuk Customer, Sales Order, dan Transaksi POS
==========================================================================
File ini berisi views untuk modul Penjualan:

CUSTOMER CRUD:
    CustomerListView   → Daftar customer
    CustomerCreateView → Tambah customer baru
    CustomerUpdateView → Edit customer
    CustomerDeleteView → Hapus customer (JSON response)

SALES ORDER CRUD:
    SalesOrderListView   → Daftar SO + summary (total nominal)
    SalesOrderCreateView → Buat SO baru + items via formset
    SalesOrderDetailView → Detail SO + items
    SalesOrderPrintView  → Cetak SO (via TemplateCetak)
    SalesOrderUpdateView → Edit SO + items formset
    SalesOrderDeleteView → Hapus SO (JSON response)

FUNCTION-BASED:
    sales_order_confirm() → Konfirmasi SO + kurangi stok

TRANSACTION (POS) - views di sini tapi model dari apps.pos:
    TransactionListView   → Daftar transaksi POS
    TransactionDetailView → Detail transaksi POS
    TransactionPrintView  → Cetak struk POS
    TransactionDeleteView → Hapus transaksi POS

⚠ CATATAN PENTING:
- Views Transaksi POS ada di file ini (bukan di apps/pos/views.py)
    karena URL transaksi berada di namespace 'penjualan'
- SO CREATE menggunakan formset standar (berbeda dari PO yang custom)
- Notifikasi Telegram dikirim saat SO baru dibuat
==========================================================================
"""

# Import dari framework Django
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
from web_project import TemplateLayout
# Import dari modul internal proyek
from apps.penjualan.models import Customer, SalesOrder, SalesOrderItem
# Import dari modul internal proyek
from apps.penjualan.forms import CustomerForm, SalesOrderForm
# Import dari modul internal proyek
from apps.core.mixins import ReadPermissionMixin, CreatePermissionMixin, UpdatePermissionMixin, DeletePermissionMixin
from django.db import transaction


# ╔══════════════════════════════════════════════════════════════╗
# ║                  CUSTOMER CRUD                                 ║
# ╚══════════════════════════════════════════════════════════════╝

class CustomerListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """Daftar semua customer. URL: /penjualan/customer/"""
    model = Customer
    # Template HTML yang digunakan untuk render halaman
    template_name = 'penjualan/customer_list.html'
    context_object_name = 'customer_list'
    # Modul permission yang dicek: 'penjualan'
    permission_module = 'penjualan'
    permission_sub_module = 'customer'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: total_customer - untuk ditampilkan di template
        context['total_customer'] = self.get_queryset().count()
        return context


class CustomerCreateView(CreatePermissionMixin, CreateView):
    """Form tambah customer. URL: /penjualan/customer/add/"""
    model = Customer
    form_class = CustomerForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'penjualan/customer_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('penjualan:customer')
    # Modul permission yang dicek: 'penjualan'
    permission_module = 'penjualan'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Tambah Customer'
        return context


    def form_valid(self, form):


        messages.success(self.request, 'Customer berhasil ditambahkan')
        return super().form_valid(form)


class CustomerUpdateView(UpdatePermissionMixin, UpdateView):
    """Form edit customer. URL: /penjualan/customer/<pk>/edit/"""
    model = Customer
    form_class = CustomerForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'penjualan/customer_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('penjualan:customer')
    # Modul permission yang dicek: 'penjualan'
    permission_module = 'penjualan'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Edit Customer'
        return context


    def form_valid(self, form):


        messages.success(self.request, 'Customer berhasil diupdate')
        return super().form_valid(form)


class CustomerDeleteView(DeletePermissionMixin, DeleteView):
    """Hapus customer - return JSON untuk AJAX."""
    model = Customer
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('penjualan:customer')
    # Modul permission yang dicek: 'penjualan'
    permission_module = 'penjualan'

    def delete(self, request, *args, **kwargs):
        """Hapus data - return JSON response untuk AJAX."""
        from django.http import JsonResponse
        self.object = self.get_object()

        # Blok penanganan error - coba jalankan kode di bawah
        try:
            customer_name = self.object.nama
            self.object.delete()
            return JsonResponse({
                'success': True, 
                'message': f'Customer {customer_name} berhasil dihapus'
            })
        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            return JsonResponse({
                'success': False, 
                'message': f'Gagal menghapus customer: {str(e)}'
            }, status=400)


    # ╔══════════════════════════════════════════════════════════════╗
    # ║                 SALES ORDER CRUD                               ║
    # ╚══════════════════════════════════════════════════════════════╝

class SalesOrderListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """
    Daftar semua Sales Order + summary metrics.
    URL: /penjualan/sales-order/
    Context: total_sales_order, total_nominal_so, customer_list (untuk filter)
    """
    model = SalesOrder
    # Template HTML yang digunakan untuk render halaman
    template_name = 'penjualan/sales_order_list.html'
    context_object_name = 'sales_order_list'
    # Modul permission yang dicek: 'penjualan'
    permission_module = 'penjualan'
    permission_sub_module = 'sales_order'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Import dari modul internal proyek
        from apps.penjualan.models import Customer
        # Import dari framework Django
        from django.db.models import Sum

        # Query database - ambil semua data context['customer_list']
        # Data konteks: customer_list - untuk ditampilkan di template
        context['customer_list'] = Customer.objects.all()

        queryset = self.get_queryset()
        # Data konteks: total_sales_order - untuk ditampilkan di template
        context['total_sales_order'] = queryset.count()
        # Data konteks: total_nominal_so - untuk ditampilkan di template
        context['total_nominal_so'] = queryset.aggregate(Sum('total_harga'))['total_harga__sum'] or 0

        return context


class SalesOrderCreateView(CreatePermissionMixin, CreateView):
    """
    Buat Sales Order baru + items via formset standar.
    URL: /penjualan/sales-order/add/

    Berbeda dari PO (yang create produk baru), SO menggunakan
    produk yang sudah ada di database.
    """
    model = SalesOrder
    form_class = SalesOrderForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'penjualan/sales_order_form.html'
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('penjualan:sales-order')
    # Modul permission yang dicek: 'penjualan'
    permission_module = 'penjualan'
    permission_sub_module = 'sales_order'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Buat Sales Order Baru'

        # Import dari modul internal proyek
        from apps.penjualan.forms import SalesOrderItemFormSet
        # Import dari modul internal proyek
        from apps.produk.models import Produk, Satuan

        # Sediakan formset item
        if self.request.POST:
            # Data konteks: formset - untuk ditampilkan di template
            context['formset'] = SalesOrderItemFormSet(self.request.POST)
        else:
            # Data konteks: formset - untuk ditampilkan di template
            context['formset'] = SalesOrderItemFormSet()

        # Query database - ambil data context['produk_list'] yang sesuai filter
        # Data konteks: produk_list - untuk ditampilkan di template
        context['produk_list'] = Produk.objects.filter(aktif=True).select_related('satuan').order_by('nama')
        # Query database - ambil semua data context['satuan_list']
        # Data konteks: satuan_list - untuk ditampilkan di template
        context['satuan_list'] = Satuan.objects.all().order_by('nama')
        return context


    def form_valid(self, form):

        context = self.get_context_data()
        # Data konteks: formset - untuk ditampilkan di template
        formset = context['formset']

        form.instance.dibuat_oleh = self.request.user

        if formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            formset.save()

            # Hitung ulang total setelah items tersimpan
            self.object.calculate_total()
            self.object.save()

            # Notifikasi Telegram (opsional)
            try:
                # Import dari modul internal proyek
                from apps.automation.signals import kirim_notifikasi_sales_order
                kirim_notifikasi_sales_order(self.object)
            # Tangkap error Exception - lanjutkan tanpa crash
            except ProtectedError:
                return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
            except Exception as e:
                pass

            # Tampilkan pesan sukses ke user
            messages.success(self.request, 'Sales Order berhasil dibuat')
            # Redirect ke halaman tujuan
            return redirect(self.success_url)
        else:
            return self.form_invalid(form)


class SalesOrderDetailView(ReadPermissionMixin, TemplateView):
    """Detail SO + items. URL: /penjualan/sales-order/<pk>/"""
    template_name = 'penjualan/sales_order_detail.html'
    # Modul permission yang dicek: 'penjualan'
    permission_module = 'penjualan'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        so_id = kwargs.get('pk')
        # Data konteks: sales_order - untuk ditampilkan di template
        context['sales_order'] = get_object_or_404(SalesOrder, pk=so_id)
        return context


class SalesOrderPrintView(ReadPermissionMixin, TemplateView):
    """Cetak SO menggunakan TemplateCetak. URL: /penjualan/sales-order/<pk>/print/"""
    template_name = 'penjualan/sales_order_print.html'
    # Modul permission yang dicek: 'penjualan'
    permission_module = 'penjualan'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = super().get_context_data(**kwargs)
        so_id = kwargs.get('pk')
        # Data konteks: sales_order - untuk ditampilkan di template
        context['sales_order'] = get_object_or_404(SalesOrder, pk=so_id)
        # Import dari modul internal proyek
        from apps.pengaturan.models import TemplateCetak, PengaturanPerusahaan
        # Data konteks: template - untuk ditampilkan di template
        context['template'] = TemplateCetak.get_template('sales_order')
        # Data konteks: perusahaan — untuk logo di header cetak
        context['perusahaan'] = PengaturanPerusahaan.load()
        return context


class SalesOrderUpdateView(UpdatePermissionMixin, UpdateView):
    """
    Edit SO + items formset.
    URL: /penjualan/sales-order/<pk>/edit/
    Recalculate total setelah items disimpan.
    ⚠ PROTEKSI: Hanya SO berstatus 'draft' yang bisa diedit.
    """
    model = SalesOrder
    form_class = SalesOrderForm
    # Template HTML yang digunakan untuk render halaman
    template_name = 'penjualan/sales_order_form.html'
    # Modul permission yang dicek: 'penjualan'
    permission_module = 'penjualan'
    permission_sub_module = 'sales_order'

    def dispatch(self, request, *args, **kwargs):
        """
        Cegah edit SO yang sudah dikonfirmasi/delivered/completed.

        Kenapa perlu proteksi ini? (Fix Maret 2026 - K4)
        Sebelumnya, SO yang sudah dikonfirmasi masih bisa diedit melalui URL langsung.
        Ini berbahaya karena:
        - Stok sudah dikurangi saat confirm → edit qty bisa bikin data stok tidak akurat
        - SO yang sudah dikirim (delivered) tidak boleh diubah

        Cara kerja:
        - dispatch() adalah method PERTAMA di CBV lifecycle (sebelum GET/POST)
        - Cek status SO → jika bukan 'draft', redirect dengan pesan error
        - Hanya SO draft yang boleh masuk ke form edit

        Terhubung dengan:
        - apps/penjualan/models.py → SalesOrder.status field
        - apps/penjualan/models.py → SalesOrder.confirm_order() yang mengubah status
        """
        so = self.get_object()
        if so.status != 'draft':
            messages.error(
                request,
                f'Sales Order {so.nomor_so} dengan status "{so.get_status_display()}" '
                f'tidak dapat diedit. Hanya SO berstatus Draft yang bisa diedit.'
            )
            return redirect('penjualan:sales-order-detail', pk=so.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        """URL redirect setelah operasi berhasil."""
        return reverse_lazy('penjualan:sales-order-detail', kwargs={'pk': self.object.pk})

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Data konteks: title - untuk ditampilkan di template
        context['title'] = 'Edit Sales Order'

        # Import dari modul internal proyek
        from apps.penjualan.forms import SalesOrderItemFormSet
        # Import dari modul internal proyek
        from apps.produk.models import Produk, Satuan

        if self.request.POST:
            # Data konteks: formset - untuk ditampilkan di template
            context['formset'] = SalesOrderItemFormSet(self.request.POST, instance=self.object)
        else:
            # Data konteks: formset - untuk ditampilkan di template
            context['formset'] = SalesOrderItemFormSet(instance=self.object)

        # Query database - ambil data context['produk_list'] yang sesuai filter
        # Data konteks: produk_list - untuk ditampilkan di template
        context['produk_list'] = Produk.objects.filter(aktif=True).select_related('satuan').order_by('nama')
        # Query database - ambil semua data context['satuan_list']
        # Data konteks: satuan_list - untuk ditampilkan di template
        context['satuan_list'] = Satuan.objects.all().order_by('nama')
        return context


    def form_valid(self, form):

        context = self.get_context_data()
        # Data konteks: formset - untuk ditampilkan di template
        formset = context['formset']

        if formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            formset.save()

            self.object.calculate_total()
            self.object.save()

            # Tampilkan pesan sukses ke user
            messages.success(self.request, 'Sales Order berhasil diupdate')
            # Redirect ke halaman tujuan
            return redirect(self.get_success_url())
        else:
            return self.form_invalid(form)


class SalesOrderDeleteView(DeletePermissionMixin, DeleteView):
    """Hapus SO - return JSON untuk AJAX."""
    model = SalesOrder
    # URL redirect setelah operasi berhasil
    success_url = reverse_lazy('penjualan:sales-order')
    # Modul permission yang dicek: 'penjualan'
    permission_module = 'penjualan'
    permission_sub_module = 'sales_order'


    def post(self, request, *args, **kwargs):

        return self.delete(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """Hapus data - return JSON response untuk AJAX."""
        from django.http import JsonResponse
        from apps.fraud_detection.signals import set_current_delete_user, clear_current_delete_user
        self.object = self.get_object()

        # Blok penanganan error - coba jalankan kode di bawah
        try:
            set_current_delete_user(request.user)
            self.object.delete()
            clear_current_delete_user()
            # Kembalikan respons JSON sukses ke klien
            return JsonResponse({'success': True, 'message': 'Sales Order berhasil dihapus'})
        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            clear_current_delete_user()
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            clear_current_delete_user()
            # Kembalikan respons JSON gagal ke klien
            return JsonResponse({'success': False, 'message': str(e)}, status=400)


# ╔══════════════════════════════════════════════════════════════╗
            # ║          FUNCTION-BASED: CONFIRM SALES ORDER                   ║
# ╚══════════════════════════════════════════════════════════════╝

# Wajib login - redirect ke login page jika belum login
@login_required
def sales_order_confirm(request, pk):
    """
    Konfirmasi Sales Order + kurangi stok dari gudang.
    URL: /penjualan/sales-order/<pk>/confirm/

    Alur:
    1. Validasi status (harus draft, bukan confirmed/delivered/cancelled)
    2. Panggil so.confirm_order() → kurangi stok per item dari gudang
    3. Log activity

    ⚠ Perbedaan dengan PO receive:
    - PO receive: TAMBAH stok ke gudang
    - SO confirm: KURANGI stok dari gudang
    """
    so = get_object_or_404(SalesOrder, pk=pk)

    if so.status == 'confirmed':
        # Tampilkan pesan error ke user
        messages.error(request, 'Order ini sudah dikonfirmasi sebelumnya')
        # Redirect ke halaman tujuan
        return redirect('penjualan:sales-order-detail', pk=pk)

    if so.status in ['delivered', 'cancelled']:
        # Tampilkan pesan error ke user
        messages.error(request, 'Order ini tidak bisa dikonfirmasi karena statusnya sudah ' + so.get_status_display())
        # Redirect ke halaman tujuan
        return redirect('penjualan:sales-order-detail', pk=pk)

    # Blok penanganan error - coba jalankan kode di bawah
    try:
        # Confirm order → kurangi stok otomatis (lihat SalesOrder.confirm_order())
        so.confirm_order(request.user)

        # Import dari modul internal proyek
        from apps.activity_log.middleware import ActivityLogMiddleware
        ActivityLogMiddleware.log_activity(
            request,
            action='update',
            model_name='Sales Order',
            object_id=so.pk,
            object_repr=str(so),
            description=f'Mengkonfirmasi Sales Order: {so.nomor_so} - stok diupdate'
        )

        # Tampilkan pesan sukses ke user
        messages.success(request, f'Sales Order {so.nomor_so} berhasil dikonfirmasi dan stok diupdate')
    # Tangkap error ValueError - lanjutkan tanpa crash
    except ValueError as e:
        # Tampilkan pesan error ke user
        messages.error(request, str(e))
    # Tangkap error Exception - lanjutkan tanpa crash
    except ProtectedError:
        return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
    except Exception as e:
        # Tampilkan pesan error ke user
        messages.error(request, f'Terjadi kesalahan: {str(e)}')

    # Redirect ke halaman tujuan
    return redirect('penjualan:sales-order-detail', pk=pk)


# ╔══════════════════════════════════════════════════════════════╗
# ║          TRANSACTION (POS) VIEWS                               ║
# ║  Model POSTransaction dari apps.pos, tapi URL di penjualan    ║
# ╚══════════════════════════════════════════════════════════════╝

class TransactionListView(ReadPermissionMixin, ListView):
    paginate_by = 50
    """
    Daftar transaksi POS/Kasir.
    URL: /penjualan/transaksi/
    ⚠ Model POSTransaction dari apps.pos, diakses via URL penjualan
    """
    template_name = 'penjualan/transaction_list.html'
    context_object_name = 'transaction_list'
    # Modul permission yang dicek: 'pos'
    permission_module = 'pos'

    def get_queryset(self):
        """Override queryset - filter atau optimasi query data."""
        from apps.pos.models import POSTransaction
        return POSTransaction.objects.all().order_by('-tanggal')

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Import dari modul internal proyek
        from apps.pos.models import POSTransaction
        # Import dari modul internal proyek
        from apps.produk.models import Gudang
        # Import dari framework Django
        from django.db.models import Sum

        # Query database - ambil data context['gudang_list'] yang sesuai filter
        # Data konteks: gudang_list - untuk ditampilkan di template
        context['gudang_list'] = Gudang.objects.filter(aktif=True)

        # Statistik untuk cards di atas tabel
        total_transaksi = POSTransaction.objects.exclude(status='cancelled').count()
        # Query database - ambil data total_pendapatan yang sesuai filter
        total_pendapatan = POSTransaction.objects.filter(
            status='paid'
        ).aggregate(Sum('total_harga'))['total_harga__sum'] or 0

        # Data konteks: total_transaksi - untuk ditampilkan di template
        context['total_transaksi'] = total_transaksi
        # Data konteks: total_pendapatan - untuk ditampilkan di template
        context['total_pendapatan'] = total_pendapatan
        # Data konteks: total_qty - jumlah total item dari semua transaksi lunas
        from apps.pos.models import POSTransactionItem
        total_qty = POSTransactionItem.objects.filter(
            transaction__status='paid'
        ).aggregate(Sum('jumlah'))['jumlah__sum'] or 0
        context['total_qty'] = total_qty

        return context


class TransactionDetailView(ReadPermissionMixin, TemplateView):
    """Detail transaksi POS. URL: /penjualan/transaksi/<pk>/"""
    template_name = 'penjualan/transaction_detail.html'
    # Modul permission yang dicek: 'pos'
    permission_module = 'pos'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        # Import dari modul internal proyek
        from apps.pos.models import POSTransaction

        transaction_id = kwargs.get('pk')
        # Data konteks: transaction - untuk ditampilkan di template
        context['transaction'] = get_object_or_404(POSTransaction, pk=transaction_id)
        return context


class TransactionPrintView(ReadPermissionMixin, TemplateView):
    """
    Cetak struk transaksi POS.
    URL: /penjualan/transaksi/<pk>/print/
    Menggunakan template 'pos/invoice_print.html' (reuse dari POS)
    """
    template_name = 'pos/invoice_print.html'
    # Modul permission yang dicek: 'pos'
    permission_module = 'pos'

    def get_context_data(self, **kwargs):
        """Menambahkan data konteks tambahan ke template."""
        context = super().get_context_data(**kwargs)
        # Import dari modul internal proyek
        from apps.pos.models import POSTransaction

        transaction_id = kwargs.get('pk')
        # Data konteks: transaction - untuk ditampilkan di template
        context['transaction'] = get_object_or_404(POSTransaction, pk=transaction_id)

        # Import dari modul internal proyek
        from apps.pengaturan.models import TemplateCetak
        # Blok penanganan error - coba jalankan kode di bawah
        try:
            # Data konteks: template - untuk ditampilkan di template
            context['template'] = TemplateCetak.get_template('pos_invoice')
        except:
            # Data konteks: template - untuk ditampilkan di template
            context['template'] = None

        return context


class TransactionDeleteView(DeletePermissionMixin, DeleteView):
    """Hapus transaksi POS - return JSON untuk AJAX."""
    success_url = reverse_lazy('penjualan:transaksi')
    # Modul permission yang dicek: 'pos'
    permission_module = 'pos'

    def get_queryset(self):
        """Override queryset - filter atau optimasi query data."""
        from apps.pos.models import POSTransaction
        return POSTransaction.objects.all()


    def post(self, request, *args, **kwargs):

        """Override post() agar memanggil delete() yang return JSON."""
        return self.delete(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        """Hapus data - return JSON response untuk AJAX."""
        from django.http import JsonResponse
        from apps.fraud_detection.signals import set_current_delete_user, clear_current_delete_user
        self.object = self.get_object()

        # Blok penanganan error - coba jalankan kode di bawah
        try:
            nomor_transaksi = self.object.nomor_transaksi
            set_current_delete_user(request.user)
            self.object.delete()
            clear_current_delete_user()
            return JsonResponse({
                'success': True, 
                'message': f'Transaksi {nomor_transaksi} berhasil dihapus'
            })
        # Tangkap error Exception - lanjutkan tanpa crash
        except ProtectedError:
            clear_current_delete_user()
            return JsonResponse({'success': False, 'message': 'Data tidak dapat dihapus karena sedang digunakan atau terkait dengan data lain.'}, status=400)
        except Exception as e:
            clear_current_delete_user()
            return JsonResponse({
                'success': False, 
                'message': f'Gagal menghapus transaksi: {str(e)}'
            }, status=400)
