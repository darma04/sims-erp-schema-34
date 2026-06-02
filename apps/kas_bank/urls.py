from django.urls import path

from . import views

app_name = "kas_bank"

urlpatterns = [
    path("", views.KasBankDashboardView.as_view(), name="dashboard"),
    path("akun/", views.KasBankAccountListView.as_view(), name="account_list"),
    path("akun/add/", views.KasBankAccountCreateView.as_view(), name="account_add"),
    path("akun/<int:pk>/", views.KasBankAccountDetailView.as_view(), name="account_detail"),
    path("akun/<int:pk>/edit/", views.KasBankAccountUpdateView.as_view(), name="account_edit"),
    path("akun/<int:pk>/delete/", views.KasBankAccountDeleteView.as_view(), name="account_delete"),
    path("mutasi/", views.KasBankTransactionListView.as_view(), name="transaction_list"),
    path("mutasi/add/", views.KasBankTransactionCreateView.as_view(), name="transaction_add"),
    path("mutasi/<int:pk>/", views.KasBankTransactionDetailView.as_view(), name="transaction_detail"),
    path("mutasi/<int:pk>/edit/", views.KasBankTransactionUpdateView.as_view(), name="transaction_edit"),
    path("mutasi/<int:pk>/delete/", views.KasBankTransactionDeleteView.as_view(), name="transaction_delete"),
    path("transfer/", views.KasBankTransferListView.as_view(), name="transfer_list"),
    path("transfer/add/", views.KasBankTransferCreateView.as_view(), name="transfer_add"),
    path("transfer/<int:pk>/", views.KasBankTransferDetailView.as_view(), name="transfer_detail"),
    path("transfer/<int:pk>/edit/", views.KasBankTransferUpdateView.as_view(), name="transfer_edit"),
    path("transfer/<int:pk>/delete/", views.KasBankTransferDeleteView.as_view(), name="transfer_delete"),
    path("rekonsiliasi/", views.KasBankReconciliationListView.as_view(), name="reconciliation_list"),
    path("rekonsiliasi/add/", views.KasBankReconciliationCreateView.as_view(), name="reconciliation_add"),
    path("rekonsiliasi/<int:pk>/", views.KasBankReconciliationDetailView.as_view(), name="reconciliation_detail"),
    path("rekonsiliasi/<int:pk>/edit/", views.KasBankReconciliationUpdateView.as_view(), name="reconciliation_edit"),
    path("rekonsiliasi/<int:pk>/delete/", views.KasBankReconciliationDeleteView.as_view(), name="reconciliation_delete"),
]
