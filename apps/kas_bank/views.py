import json
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, TemplateView, UpdateView

from apps.core.mixins import CreatePermissionMixin, DeletePermissionMixin, ReadPermissionMixin, UpdatePermissionMixin
from apps.akuntansi.models import Akun
from web_project import TemplateLayout
from .forms import (
    KasBankAccountForm,
    KasBankReconciliationForm,
    KasBankTransactionForm,
    KasBankTransferForm,
)
from .models import KasBankAccount, KasBankReconciliation, KasBankTransaction, KasBankTransfer
from .services import post_kas_bank_transfer, post_manual_kas_bank_transaction


def _sum_decimal(queryset, field):
    return queryset.aggregate(total=Sum(field))["total"] or Decimal("0")


class KasBankDashboardView(ReadPermissionMixin, TemplateView):
    template_name = "kas_bank/dashboard.html"
    permission_module = "kas_bank"
    permission_sub_module = "dashboard"

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        accounts = KasBankAccount.objects.all()
        active_accounts_qs = accounts.filter(aktif=True)
        posted_mutasi = KasBankTransaction.objects.filter(status="posted")
        masuk = posted_mutasi.filter(tipe__in=["masuk", "transfer_masuk", "penyesuaian_masuk"])
        keluar = posted_mutasi.filter(tipe__in=["keluar", "transfer_keluar", "penyesuaian_keluar"])
        status_labels = dict(KasBankTransaction.STATUS_CHOICES)

        account_cards = []
        for account in active_accounts_qs.order_by("kode"):
            account_cards.append(
                {
                    "account": account,
                    "saldo": account.saldo_terhitung,
                    "masuk": account.total_masuk,
                    "keluar": account.total_keluar,
                }
            )

        total_masuk = _sum_decimal(masuk, "jumlah")
        total_keluar = _sum_decimal(keluar, "jumlah")
        net_cashflow = total_masuk - total_keluar
        status_summary = [
            {"status": status_labels.get(row["status"], row["status"]), "total": row["total"]}
            for row in KasBankTransaction.objects.values("status")
            .annotate(total=Count("id"))
            .order_by("status")
        ]

        context.update(
            {
                "total_accounts": accounts.count(),
                "active_accounts": active_accounts_qs.count(),
                "total_saldo_aktif": (
                    _sum_decimal(active_accounts_qs, "saldo_awal")
                    + _sum_decimal(masuk.filter(akun_kas_bank__aktif=True), "jumlah")
                    - _sum_decimal(keluar.filter(akun_kas_bank__aktif=True), "jumlah")
                ),
                "total_masuk": total_masuk,
                "total_keluar": total_keluar,
                "pending_reconciliation": KasBankReconciliation.objects.filter(status="draft").count(),
                "recent_transactions": posted_mutasi.select_related("akun_kas_bank", "cabang").order_by("-tanggal")[:50],
                "account_cards": account_cards,
                "status_summary": status_summary,
                "status_chart_labels": json.dumps([row["status"] for row in status_summary]),
                "status_chart_values": json.dumps([row["total"] for row in status_summary]),
                "cashflow_chart_labels": json.dumps(["Masuk", "Keluar", "Net Cashflow"]),
                "cashflow_chart_values": json.dumps([float(total_masuk), float(total_keluar), float(net_cashflow)]),
            }
        )
        context["net_cashflow"] = net_cashflow
        return context


class KasBankAccountListView(ReadPermissionMixin, ListView):
    model = KasBankAccount
    template_name = "kas_bank/account_list.html"
    context_object_name = "accounts"
    permission_module = "kas_bank"
    permission_sub_module = "akun"

    def get_queryset(self):
        qs = KasBankAccount.objects.select_related("akun").order_by("kode")
        tipe = self.request.GET.get("tipe")
        status = self.request.GET.get("status")
        akun = self.request.GET.get("akun")
        q = self.request.GET.get("q")
        if tipe:
            qs = qs.filter(tipe=tipe)
        if status == "aktif":
            qs = qs.filter(aktif=True)
        elif status == "nonaktif":
            qs = qs.filter(aktif=False)
        if akun:
            qs = qs.filter(akun_id=akun)
        if q:
            qs = qs.filter(Q(kode__icontains=q) | Q(nama__icontains=q) | Q(nama_bank__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        accounts = self.get_queryset()
        context.update(
            {
                "total_accounts": accounts.count(),
                "active_accounts": accounts.filter(aktif=True).count(),
                "total_saldo_awal": _sum_decimal(accounts, "saldo_awal"),
                "default_accounts": accounts.filter(is_default=True).count(),
                "tipe_choices": KasBankAccount.TIPE_CHOICES,
                "coa_accounts": Akun.objects.filter(is_active=True).order_by("kode"),
            }
        )
        return context


class KasBankAccountCreateView(CreatePermissionMixin, CreateView):
    model = KasBankAccount
    form_class = KasBankAccountForm
    template_name = "kas_bank/account_form.html"
    success_url = reverse_lazy("kas_bank:account_list")
    permission_module = "kas_bank"
    permission_sub_module = "akun"

    def form_valid(self, form):
        form.instance.dibuat_oleh = self.request.user
        response = super().form_valid(form)
        # Sinkronisasi saldo awal dengan jurnal accounting
        if self.object.saldo_awal and self.object.saldo_awal > 0:
            try:
                from apps.kas_bank.services import sync_saldo_awal_jurnal
                sync_saldo_awal_jurnal(self.object, user=self.request.user)
            except Exception as e:
                messages.warning(self.request, f"Akun berhasil dibuat, tapi jurnal saldo awal gagal: {e}")
        messages.success(self.request, "Akun Kas/Bank berhasil dibuat.")
        return response

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context["title"] = "Tambah Akun Kas/Bank"
        return context


class KasBankAccountDetailView(ReadPermissionMixin, DetailView):
    model = KasBankAccount
    template_name = "kas_bank/account_detail.html"
    context_object_name = "account"
    permission_module = "kas_bank"
    permission_sub_module = "akun"

    def get_queryset(self):
        return KasBankAccount.objects.select_related("akun", "dibuat_oleh")

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context["recent_transactions"] = self.object.mutasi.select_related(
            "akun_lawan", "cabang", "jurnal_entry"
        ).order_by("-tanggal", "-id")[:25]
        return context


class KasBankAccountUpdateView(UpdatePermissionMixin, UpdateView):
    model = KasBankAccount
    form_class = KasBankAccountForm
    template_name = "kas_bank/account_form.html"
    success_url = reverse_lazy("kas_bank:account_list")
    permission_module = "kas_bank"
    permission_sub_module = "akun"

    def form_valid(self, form):
        old_saldo_awal = KasBankAccount.objects.filter(pk=self.object.pk).values_list('saldo_awal', flat=True).first()
        response = super().form_valid(form)
        # Sinkronisasi saldo awal jika berubah
        new_saldo_awal = self.object.saldo_awal
        if old_saldo_awal != new_saldo_awal:
            try:
                from apps.kas_bank.services import sync_saldo_awal_jurnal
                sync_saldo_awal_jurnal(self.object, user=self.request.user)
            except Exception as e:
                messages.warning(self.request, f"Akun berhasil diperbarui, tapi jurnal saldo awal gagal disinkronkan: {e}")
        messages.success(self.request, "Akun Kas/Bank berhasil diperbarui.")
        return response

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context["title"] = "Edit Akun Kas/Bank"
        return context


class KasBankAccountDeleteView(DeletePermissionMixin, DeleteView):
    model = KasBankAccount
    success_url = reverse_lazy("kas_bank:account_list")
    permission_module = "kas_bank"
    permission_sub_module = "akun"

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.mutasi.exists():
            return JsonResponse(
                {"success": False, "message": "Akun tidak dapat dihapus karena sudah memiliki mutasi."},
                status=400,
            )
        self.object.delete()
        return JsonResponse({"success": True, "message": "Akun Kas/Bank berhasil dihapus."})


class KasBankTransactionListView(ReadPermissionMixin, ListView):
    model = KasBankTransaction
    template_name = "kas_bank/transaction_list.html"
    context_object_name = "transactions"
    permission_module = "kas_bank"
    permission_sub_module = "mutasi"

    def get_queryset(self):
        qs = KasBankTransaction.objects.select_related("akun_kas_bank", "akun_lawan", "cabang", "metode_pembayaran")
        account = self.request.GET.get("account")
        tipe = self.request.GET.get("tipe")
        status = self.request.GET.get("status")
        q = self.request.GET.get("q")
        if account:
            qs = qs.filter(akun_kas_bank_id=account)
        if tipe:
            qs = qs.filter(tipe=tipe)
        if status:
            qs = qs.filter(status=status)
        if q:
            qs = qs.filter(Q(nomor__icontains=q) | Q(deskripsi__icontains=q) | Q(sumber_ref__icontains=q))
        return qs.order_by("-tanggal", "-id")

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        qs = self.get_queryset()
        masuk = qs.filter(tipe__in=["masuk", "transfer_masuk", "penyesuaian_masuk"], status="posted")
        keluar = qs.filter(tipe__in=["keluar", "transfer_keluar", "penyesuaian_keluar"], status="posted")
        context.update(
            {
                "accounts": KasBankAccount.objects.filter(aktif=True).order_by("kode"),
                "tipe_choices": KasBankTransaction.TIPE_CHOICES,
                "status_choices": KasBankTransaction.STATUS_CHOICES,
                "total_masuk": _sum_decimal(masuk, "jumlah"),
                "total_keluar": _sum_decimal(keluar, "jumlah"),
                "total_rows": qs.count(),
            }
        )
        context["net_cashflow"] = context["total_masuk"] - context["total_keluar"]
        return context


class KasBankTransactionCreateView(CreatePermissionMixin, CreateView):
    model = KasBankTransaction
    form_class = KasBankTransactionForm
    template_name = "kas_bank/transaction_form.html"
    success_url = reverse_lazy("kas_bank:transaction_list")
    permission_module = "kas_bank"
    permission_sub_module = "mutasi"

    def form_valid(self, form):
        try:
            with transaction.atomic():
                self.object = form.save(commit=False)
                self.object.dibuat_oleh = self.request.user
                self.object.save()
                post_manual_kas_bank_transaction(self.object, user=self.request.user)
        except Exception as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Mutasi Kas/Bank berhasil dibuat.")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context["title"] = "Tambah Mutasi Kas/Bank"
        return context


class KasBankTransactionDetailView(ReadPermissionMixin, DetailView):
    model = KasBankTransaction
    template_name = "kas_bank/transaction_detail.html"
    context_object_name = "transaction"
    permission_module = "kas_bank"
    permission_sub_module = "mutasi"

    def get_queryset(self):
        return KasBankTransaction.objects.select_related(
            "akun_kas_bank", "akun_lawan", "cabang", "metode_pembayaran", "jurnal_entry", "dibuat_oleh"
        )

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        tx = self.object
        # Baris jurnal terkait (untuk audit trail)
        if tx.jurnal_entry_id:
            context["jurnal_lines"] = tx.jurnal_entry.lines.select_related("akun").all()
        else:
            context["jurnal_lines"] = []
        # Mutasi terkait (jika sumber adalah transfer, tampilkan pasangan mutasi)
        if tx.sumber_app == "kas_bank" and tx.sumber_model == "KasBankTransfer" and tx.sumber_id:
            context["related_transactions"] = KasBankTransaction.objects.filter(
                sumber_app="kas_bank",
                sumber_model="KasBankTransfer",
                sumber_id=tx.sumber_id,
            ).exclude(pk=tx.pk).select_related("akun_kas_bank")
        else:
            context["related_transactions"] = []
        return context


class KasBankTransactionUpdateView(UpdatePermissionMixin, UpdateView):
    model = KasBankTransaction
    form_class = KasBankTransactionForm
    template_name = "kas_bank/transaction_form.html"
    success_url = reverse_lazy("kas_bank:transaction_list")
    permission_module = "kas_bank"
    permission_sub_module = "mutasi"

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.jurnal_entry_id:
            messages.error(request, "Mutasi yang sudah memiliki jurnal tidak dapat diedit.")
            return redirect("kas_bank:transaction_list")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        try:
            with transaction.atomic():
                self.object = form.save()
                post_manual_kas_bank_transaction(self.object, user=self.request.user)
        except Exception as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Mutasi Kas/Bank berhasil diperbarui.")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context["title"] = "Edit Mutasi Kas/Bank"
        return context


class KasBankTransactionDeleteView(DeletePermissionMixin, DeleteView):
    model = KasBankTransaction
    success_url = reverse_lazy("kas_bank:transaction_list")
    permission_module = "kas_bank"
    permission_sub_module = "mutasi"

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.jurnal_entry_id:
            return JsonResponse(
                {"success": False, "message": "Mutasi yang sudah memiliki jurnal tidak dapat dihapus."},
                status=400,
            )
        self.object.delete()
        return JsonResponse({"success": True, "message": "Mutasi Kas/Bank berhasil dihapus."})


class KasBankTransferListView(ReadPermissionMixin, ListView):
    model = KasBankTransfer
    template_name = "kas_bank/transfer_list.html"
    context_object_name = "transfers"
    permission_module = "kas_bank"
    permission_sub_module = "transfer"

    def get_queryset(self):
        qs = KasBankTransfer.objects.select_related("dari_akun", "ke_akun", "cabang").order_by("-tanggal", "-id")
        status = self.request.GET.get("status")
        dari_akun = self.request.GET.get("dari_akun")
        ke_akun = self.request.GET.get("ke_akun")
        q = self.request.GET.get("q")
        if status:
            qs = qs.filter(status=status)
        if dari_akun:
            qs = qs.filter(dari_akun_id=dari_akun)
        if ke_akun:
            qs = qs.filter(ke_akun_id=ke_akun)
        if q:
            qs = qs.filter(
                Q(nomor__icontains=q)
                | Q(catatan__icontains=q)
                | Q(dari_akun__kode__icontains=q)
                | Q(dari_akun__nama__icontains=q)
                | Q(ke_akun__kode__icontains=q)
                | Q(ke_akun__nama__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        qs = self.get_queryset()
        context.update(
            {
                "accounts": KasBankAccount.objects.filter(aktif=True).order_by("kode"),
                "status_choices": KasBankTransfer.STATUS_CHOICES,
                "posted_count": qs.filter(status="posted").count(),
                "total_transfer": _sum_decimal(qs.filter(status="posted"), "jumlah"),
                "total_biaya_admin": _sum_decimal(qs.filter(status="posted"), "biaya_admin"),
                "total_rows": qs.count(),
            }
        )
        return context


class KasBankTransferCreateView(CreatePermissionMixin, CreateView):
    model = KasBankTransfer
    form_class = KasBankTransferForm
    template_name = "kas_bank/transfer_form.html"
    success_url = reverse_lazy("kas_bank:transfer_list")
    permission_module = "kas_bank"
    permission_sub_module = "transfer"

    def form_valid(self, form):
        try:
            with transaction.atomic():
                self.object = form.save(commit=False)
                self.object.dibuat_oleh = self.request.user
                self.object.save()
                post_kas_bank_transfer(self.object, user=self.request.user)
        except Exception as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Transfer Kas/Bank berhasil dibuat.")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context["title"] = "Tambah Transfer Kas/Bank"
        return context


class KasBankTransferDetailView(ReadPermissionMixin, DetailView):
    model = KasBankTransfer
    template_name = "kas_bank/transfer_detail.html"
    context_object_name = "transfer"
    permission_module = "kas_bank"
    permission_sub_module = "transfer"

    def get_queryset(self):
        return KasBankTransfer.objects.select_related(
            "dari_akun", "ke_akun", "akun_biaya_admin", "cabang", "jurnal_entry", "dibuat_oleh"
        )

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context["mutasi_list"] = KasBankTransaction.objects.filter(
            sumber_app="kas_bank",
            sumber_model="KasBankTransfer",
            sumber_id=self.object.pk,
        ).select_related("akun_kas_bank").order_by("tipe")
        return context


class KasBankTransferUpdateView(UpdatePermissionMixin, UpdateView):
    model = KasBankTransfer
    form_class = KasBankTransferForm
    template_name = "kas_bank/transfer_form.html"
    success_url = reverse_lazy("kas_bank:transfer_list")
    permission_module = "kas_bank"
    permission_sub_module = "transfer"

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.jurnal_entry_id:
            messages.error(request, "Transfer yang sudah memiliki jurnal tidak dapat diedit.")
            return redirect("kas_bank:transfer_list")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        try:
            with transaction.atomic():
                self.object = form.save()
                post_kas_bank_transfer(self.object, user=self.request.user)
        except Exception as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Transfer Kas/Bank berhasil diperbarui.")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context["title"] = "Edit Transfer Kas/Bank"
        return context


class KasBankTransferDeleteView(DeletePermissionMixin, DeleteView):
    model = KasBankTransfer
    success_url = reverse_lazy("kas_bank:transfer_list")
    permission_module = "kas_bank"
    permission_sub_module = "transfer"

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.jurnal_entry_id:
            return JsonResponse(
                {"success": False, "message": "Transfer yang sudah memiliki jurnal tidak dapat dihapus."},
                status=400,
            )
        self.object.delete()
        return JsonResponse({"success": True, "message": "Transfer Kas/Bank berhasil dihapus."})


class KasBankReconciliationListView(ReadPermissionMixin, ListView):
    model = KasBankReconciliation
    template_name = "kas_bank/reconciliation_list.html"
    context_object_name = "reconciliations"
    permission_module = "kas_bank"
    permission_sub_module = "rekonsiliasi"

    def get_queryset(self):
        qs = KasBankReconciliation.objects.select_related("akun_kas_bank").order_by("-tanggal_akhir", "-id")
        status = self.request.GET.get("status")
        account = self.request.GET.get("account")
        tanggal_akhir = self.request.GET.get("tanggal_akhir")
        q = self.request.GET.get("q")
        if status:
            qs = qs.filter(status=status)
        if account:
            qs = qs.filter(akun_kas_bank_id=account)
        if tanggal_akhir:
            qs = qs.filter(tanggal_akhir__lte=tanggal_akhir)
        if q:
            qs = qs.filter(
                Q(akun_kas_bank__kode__icontains=q)
                | Q(akun_kas_bank__nama__icontains=q)
                | Q(catatan__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        qs = self.get_queryset()
        context.update(
            {
                "accounts": KasBankAccount.objects.filter(aktif=True).order_by("kode"),
                "status_choices": KasBankReconciliation.STATUS_CHOICES,
                "draft_count": qs.filter(status="draft").count(),
                "reconciled_count": qs.filter(status="reconciled").count(),
                "total_rows": qs.count(),
                "total_selisih": _sum_decimal(qs, "selisih"),
            }
        )
        return context


class KasBankReconciliationCreateView(CreatePermissionMixin, CreateView):
    model = KasBankReconciliation
    form_class = KasBankReconciliationForm
    template_name = "kas_bank/reconciliation_form.html"
    success_url = reverse_lazy("kas_bank:reconciliation_list")
    permission_module = "kas_bank"
    permission_sub_module = "rekonsiliasi"

    def form_valid(self, form):
        form.instance.dibuat_oleh = self.request.user
        messages.success(self.request, "Rekonsiliasi Kas/Bank berhasil dibuat.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context["title"] = "Tambah Rekonsiliasi Kas/Bank"
        return context


class KasBankReconciliationDetailView(ReadPermissionMixin, DetailView):
    model = KasBankReconciliation
    template_name = "kas_bank/reconciliation_detail.html"
    context_object_name = "reconciliation"
    permission_module = "kas_bank"
    permission_sub_module = "rekonsiliasi"

    def get_queryset(self):
        return KasBankReconciliation.objects.select_related("akun_kas_bank", "dibuat_oleh")

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context["transactions"] = KasBankTransaction.objects.filter(
            akun_kas_bank=self.object.akun_kas_bank,
            status="posted",
            tanggal__date__gte=self.object.tanggal_mulai,
            tanggal__date__lte=self.object.tanggal_akhir,
        ).order_by("-tanggal", "-id")[:50]
        return context


class KasBankReconciliationUpdateView(UpdatePermissionMixin, UpdateView):
    model = KasBankReconciliation
    form_class = KasBankReconciliationForm
    template_name = "kas_bank/reconciliation_form.html"
    success_url = reverse_lazy("kas_bank:reconciliation_list")
    permission_module = "kas_bank"
    permission_sub_module = "rekonsiliasi"

    def form_valid(self, form):
        messages.success(self.request, "Rekonsiliasi Kas/Bank berhasil diperbarui.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context["title"] = "Edit Rekonsiliasi Kas/Bank"
        return context


class KasBankReconciliationDeleteView(DeletePermissionMixin, DeleteView):
    model = KasBankReconciliation
    success_url = reverse_lazy("kas_bank:reconciliation_list")
    permission_module = "kas_bank"
    permission_sub_module = "rekonsiliasi"

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        self.object.delete()
        return JsonResponse({"success": True, "message": "Rekonsiliasi Kas/Bank berhasil dihapus."})
