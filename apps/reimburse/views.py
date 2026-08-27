from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView

from web_project import TemplateLayout
from apps.core.mixins import SubModulePermissionMixin
from .models import ReimburseRequest, ReimburseItem
from .forms import ReimburseForm, ReimburseItemFormSet, ReimbursePayForm


class ReimburseListView(SubModulePermissionMixin, LoginRequiredMixin, ListView):
    model = ReimburseRequest
    template_name = 'reimburse/reimburse_list.html'
    context_object_name = 'reimburse_list'
    permission_module = 'reimburse'
    permission_sub_module = 'daftar_reimburse'
    permission_action = 'read'

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.GET.get('search', '')
        status_filter = self.request.GET.get('status', '')
        if search:
            qs = qs.filter(nomor__icontains=search) | qs.filter(
                pemohon__username__icontains=search
            ) | qs.filter(keterangan__icontains=search)
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['status_filter'] = self.request.GET.get('status', '')
        context['search_query'] = self.request.GET.get('search', '')
        qs = self.get_queryset()
        context['total_reimburse'] = qs.count()
        from django.db.models import Sum
        total_nominal = qs.aggregate(total=Sum('total'))['total']
        context['total_nominal'] = total_nominal or 0
        return context


class ReimburseDetailView(SubModulePermissionMixin, LoginRequiredMixin, DetailView):
    model = ReimburseRequest
    template_name = 'reimburse/reimburse_detail.html'
    context_object_name = 'reimburse'
    permission_module = 'reimburse'
    permission_sub_module = 'daftar_reimburse'
    permission_action = 'read'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['reimburse'] = self.object
        from apps.pos.models import MetodePembayaran
        context['metode_list'] = MetodePembayaran.objects.filter(aktif=True)
        return context


class ReimburseCreateView(SubModulePermissionMixin, LoginRequiredMixin, CreateView):
    model = ReimburseRequest
    form_class = ReimburseForm
    template_name = 'reimburse/reimburse_form.html'
    permission_module = 'reimburse'
    permission_sub_module = 'pengajuan_reimburse'
    permission_action = 'create'

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Tambah Reimburse'
        context['item_formset'] = kwargs.get('item_formset', ReimburseItemFormSet())
        return context

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        item_formset = ReimburseItemFormSet(request.POST, request.FILES)
        if form.is_valid() and item_formset.is_valid():
            return self.form_valid(form, item_formset)
        return self.form_invalid(form, item_formset)

    def form_valid(self, form, item_formset):
        with db_transaction.atomic():
            self.object = form.save(commit=False)
            self.object.pemohon = self.request.user
            self.object.dibuat_oleh = self.request.user
            total = sum(
                item_form.cleaned_data.get('nominal', 0) or 0
                for item_form in item_formset
                if not item_form.cleaned_data.get('DELETE', False)
            )
            self.object.total = total
            self.object.save()
            item_formset.instance = self.object
            item_formset.save()
        messages.success(self.request, f'Reimburse {self.object.nomor} berhasil dibuat.')
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form, item_formset):
        return self.render_to_response(
            self.get_context_data(form=form, item_formset=item_formset)
        )

    def get_success_url(self):
        return reverse('reimburse:detail', kwargs={'pk': self.object.pk})


class ReimburseUpdateView(SubModulePermissionMixin, LoginRequiredMixin, UpdateView):
    model = ReimburseRequest
    form_class = ReimburseForm
    template_name = 'reimburse/reimburse_form.html'
    permission_module = 'reimburse'
    permission_sub_module = 'pengajuan_reimburse'
    permission_action = 'update'

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.status not in ['draft', 'rejected']:
            messages.error(request, f'Tidak dapat mengedit reimburse dengan status "{self.object.get_status_display()}".')
            return redirect('reimburse:detail', pk=self.object.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = TemplateLayout.init(self, super().get_context_data(**kwargs))
        context['title'] = 'Edit Reimburse'
        context['item_formset'] = kwargs.get('item_formset', ReimburseItemFormSet(instance=self.object))
        context['is_readonly'] = self.object.status not in ['draft', 'rejected']
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        item_formset = ReimburseItemFormSet(request.POST, request.FILES, instance=self.object)
        if form.is_valid() and item_formset.is_valid():
            return self.form_valid(form, item_formset)
        return self.form_invalid(form, item_formset)

    def form_valid(self, form, item_formset):
        with db_transaction.atomic():
            self.object = form.save(commit=False)
            total = sum(
                item_form.cleaned_data.get('nominal', 0) or 0
                for item_form in item_formset
                if not item_form.cleaned_data.get('DELETE', False)
            )
            self.object.total = total
            self.object.save()
            item_formset.save()
        messages.success(self.request, f'Reimburse {self.object.nomor} berhasil diperbarui.')
        return HttpResponseRedirect(self.get_success_url())

    def form_invalid(self, form, item_formset):
        return self.render_to_response(
            self.get_context_data(form=form, item_formset=item_formset)
        )

    def get_success_url(self):
        return reverse('reimburse:detail', kwargs={'pk': self.object.pk})


class ReimburseActionView(SubModulePermissionMixin, LoginRequiredMixin, View):
    permission_module = 'reimburse'
    permission_sub_module = 'pengajuan_reimburse'
    permission_action = 'update'

    def post(self, request, pk):
        reimburse = get_object_or_404(ReimburseRequest, pk=pk)
        action = request.POST.get('action')

        try:
            if action == 'submit':
                return self._submit(reimburse, request)
            elif action == 'approve':
                return self._approve(reimburse, request)
            elif action == 'reject':
                return self._reject(reimburse, request)
            elif action == 'pay':
                return self._pay(reimburse, request)
            elif action == 'cancel':
                return self._cancel(reimburse, request)
            elif action == 'complete':
                return self._complete(reimburse, request)
            else:
                return JsonResponse({'success': False, 'message': 'Aksi tidak dikenal.'}, status=400)
        except ValidationError as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)

    def _submit(self, obj, request):
        if obj.status != 'draft' and obj.status != 'rejected':
            raise ValidationError(f'Tidak dapat mengajukan reimburse dengan status "{obj.get_status_display()}".')
        if obj.items.count() == 0:
            raise ValidationError('Reimburse harus memiliki minimal 1 item.')
        obj.transition_status('submitted')
        obj.save()
        messages.success(request, f'Reimburse {obj.nomor} berhasil diajukan.')
        return redirect('reimburse:detail', pk=obj.pk)

    def _approve(self, obj, request):
        if obj.status != 'submitted':
            raise ValidationError(f'Tidak dapat menyetujui reimburse dengan status "{obj.get_status_display()}".')
        obj.transition_status('approved')
        obj.approved_by = request.user
        obj.approved_at = timezone.now()
        obj.save()
        messages.success(request, f'Reimburse {obj.nomor} berhasil disetujui.')
        return redirect('reimburse:detail', pk=obj.pk)

    def _reject(self, obj, request):
        if obj.status != 'submitted':
            raise ValidationError(f'Tidak dapat menolak reimburse dengan status "{obj.get_status_display()}".')
        alasan = request.POST.get('alasan', '').strip()
        if not alasan:
            raise ValidationError('Alasan penolakan wajib diisi.')
        obj.transition_status('rejected')
        obj.rejection_reason = alasan
        obj.save()
        messages.warning(request, f'Reimburse {obj.nomor} ditolak.')
        return redirect('reimburse:detail', pk=obj.pk)

    def _pay(self, obj, request):
        if obj.status != 'approved':
            raise ValidationError(f'Tidak dapat membayar reimburse dengan status "{obj.get_status_display()}".')
        if not obj.metode_pembayaran:
            form = ReimbursePayForm(request.POST)
            if form.is_valid():
                obj.metode_pembayaran = form.cleaned_data['metode_pembayaran']
                obj.tanggal_bayar = form.cleaned_data['tanggal_bayar']
            else:
                raise ValidationError('Metode pembayaran dan tanggal bayar wajib diisi.')

        from apps.kas_bank.services import resolve_kas_bank_mapping
        kas_account, _, _ = resolve_kas_bank_mapping(obj.metode_pembayaran)
        if obj.total > kas_account.saldo_terhitung:
            raise ValidationError(
                f'Saldo {kas_account.nama} tidak mencukupi. '
                f'Tersedia: Rp {kas_account.saldo_terhitung:,.0f}, Dibutuhkan: Rp {obj.total:,.0f}'
            )

        obj.transition_status('paid')
        if not obj.tanggal_bayar:
            obj.tanggal_bayar = timezone.now().date()
        obj.save()
        messages.success(request, f'Reimburse {obj.nomor} berhasil dibayar.')
        return redirect('reimburse:detail', pk=obj.pk)

    def _cancel(self, obj, request):
        if obj.status not in ['draft', 'submitted', 'approved', 'paid']:
            raise ValidationError(f'Tidak dapat membatalkan reimburse dengan status "{obj.get_status_display()}".')
        obj.transition_status('cancelled')
        obj.cancelled_by = request.user
        obj.cancelled_at = timezone.now()
        obj.save()
        messages.warning(request, f'Reimburse {obj.nomor} dibatalkan.')
        return redirect('reimburse:detail', pk=obj.pk)

    def _complete(self, obj, request):
        if obj.status != 'paid':
            raise ValidationError(f'Tidak dapat menyelesaikan reimburse dengan status "{obj.get_status_display()}".')
        obj.transition_status('completed')
        obj.save()
        messages.success(request, f'Reimburse {obj.nomor} selesai.')
        return redirect('reimburse:detail', pk=obj.pk)


class ReimburseDeleteView(SubModulePermissionMixin, LoginRequiredMixin, DeleteView):
    model = ReimburseRequest
    permission_module = 'reimburse'
    permission_sub_module = 'daftar_reimburse'
    permission_action = 'delete'

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.status not in ['draft', 'rejected']:
            return JsonResponse({
                'success': False,
                'message': f'Tidak dapat menghapus reimburse dengan status "{self.object.get_status_display()}".'
            }, status=400)
        try:
            self.object.delete()
            return JsonResponse({'success': True, 'message': 'Reimburse berhasil dihapus.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
