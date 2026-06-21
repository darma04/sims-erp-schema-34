from django import forms

from apps.akuntansi.models import Akun
from apps.produk.models import Gudang
from .models import KasBankAccount, KasBankReconciliation, KasBankTransaction, KasBankTransfer


class BootstrapModelForm(forms.ModelForm):
    select_widgets = (forms.Select, forms.SelectMultiple)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                css_class = "form-check-input"
            elif isinstance(field.widget, self.select_widgets):
                css_class = "form-select"
            else:
                css_class = "form-control"
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {css_class}".strip()


class KasBankAccountForm(BootstrapModelForm):
    class Meta:
        model = KasBankAccount
        fields = [
            "kode",
            "nama",
            "tipe",
            "akun",
            "nomor_rekening",
            "nama_bank",
            "nama_pemilik",
            "saldo_awal",
            "aktif",
            "is_default",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["akun"].queryset = Akun.objects.filter(is_active=True).order_by("kode")


class KasBankTransactionForm(BootstrapModelForm):
    class Meta:
        model = KasBankTransaction
        fields = [
            "tanggal",
            "akun_kas_bank",
            "tipe",
            "deskripsi",
            "jumlah",
            "akun_lawan",
            "cabang",
            "metode_pembayaran",
            "sumber_ref",
            "status",
            "catatan",
        ]
        widgets = {
            "tanggal": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "catatan": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["akun_kas_bank"].queryset = KasBankAccount.objects.filter(aktif=True).order_by("kode")
        self.fields["akun_lawan"].queryset = Akun.objects.filter(is_active=True).order_by("kode")
        self.fields["cabang"].queryset = Gudang.objects.filter(aktif=True).order_by("nama")

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        tipe = cleaned.get("tipe")
        jumlah = cleaned.get("jumlah")
        akun_lawan = cleaned.get("akun_lawan")

        if jumlah is not None and jumlah <= 0:
            raise forms.ValidationError("Jumlah mutasi harus lebih dari 0.")
        if status == "posted" and tipe in ["masuk", "keluar", "penyesuaian_masuk", "penyesuaian_keluar"] and not akun_lawan:
            raise forms.ValidationError("Akun lawan wajib diisi untuk mutasi yang langsung diposting.")
        return cleaned


class KasBankTransferForm(BootstrapModelForm):
    class Meta:
        model = KasBankTransfer
        fields = [
            "tanggal",
            "dari_akun",
            "ke_akun",
            "jumlah",
            "biaya_admin",
            "akun_biaya_admin",
            "cabang",
            "status",
            "catatan",
        ]
        widgets = {
            "tanggal": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "catatan": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        accounts = KasBankAccount.objects.filter(aktif=True).order_by("kode")
        self.fields["dari_akun"].queryset = accounts
        self.fields["ke_akun"].queryset = accounts
        self.fields["akun_biaya_admin"].queryset = Akun.objects.filter(is_active=True).order_by("kode")
        self.fields["cabang"].queryset = Gudang.objects.filter(aktif=True).order_by("nama")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("dari_akun") and cleaned.get("ke_akun") and cleaned["dari_akun"] == cleaned["ke_akun"]:
            raise forms.ValidationError("Akun sumber dan tujuan transfer tidak boleh sama.")
        if cleaned.get("jumlah") is not None and cleaned["jumlah"] <= 0:
            raise forms.ValidationError("Jumlah transfer harus lebih dari 0.")
        if cleaned.get("biaya_admin") is not None and cleaned["biaya_admin"] < 0:
            raise forms.ValidationError("Biaya admin tidak boleh negatif.")
        return cleaned


class KasBankReconciliationForm(BootstrapModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Auto-populate saldo_sistem from akun's saldo_terhitung
        if self.instance and self.instance.akun_kas_bank_id:
            if not self.instance.saldo_sistem or self.instance.saldo_sistem == 0:
                try:
                    self.instance.saldo_sistem = self.instance.akun_kas_bank.saldo_terhitung
                    self.initial['saldo_sistem'] = self.instance.saldo_sistem
                except Exception:
                    pass
        # Also handle when akun is selected via form data
        akun_id = self.data.get('akun_kas_bank') or (self.instance.akun_kas_bank_id if self.instance else None)
        if akun_id and (not self.instance.saldo_sistem or self.instance.saldo_sistem == 0):
            try:
                from apps.kas_bank.models import KasBankAccount
                akun = KasBankAccount.objects.get(pk=akun_id)
                self.initial['saldo_sistem'] = akun.saldo_terhitung
            except Exception:
                pass
    class Meta:
        model = KasBankReconciliation
        fields = [
            "akun_kas_bank",
            "tanggal_mulai",
            "tanggal_akhir",
            "saldo_sistem",
            "saldo_statement",
            "status",
            "catatan",
        ]
        widgets = {
            "tanggal_mulai": forms.DateInput(attrs={"type": "date"}),
            "tanggal_akhir": forms.DateInput(attrs={"type": "date"}),
            "catatan": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["akun_kas_bank"].queryset = KasBankAccount.objects.filter(aktif=True).order_by("kode")
