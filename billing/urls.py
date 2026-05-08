from django.urls import path

from billing import views

app_name = 'billing'

urlpatterns = [
    # Monthly billing ledger
    path('', views.monthly_view, name='monthly_view'),
    path('add/', views.bill_create, name='bill_create'),
    path('inline-add/', views.bill_inline_create, name='bill_inline_create'),
    path('<int:pk>/edit/', views.bill_update, name='bill_update'),
    path('<int:pk>/payment/', views.bill_record_payment, name='bill_record_payment'),
    path('<int:pk>/delete/', views.bill_delete, name='bill_delete'),

    # Expenses & reimbursements
    path('expenses/', views.expense_view, name='expense_view'),
    path('expenses/add/', views.expense_create, name='expense_create'),
    path('expenses/inline-add/', views.expense_inline_create, name='expense_inline_create'),
    path('expenses/<int:pk>/edit/', views.expense_update, name='expense_update'),
    path('expenses/<int:pk>/delete/', views.expense_delete, name='expense_delete'),
    path('expenses/<int:pk>/reimbursed/', views.expense_mark_reimbursed, name='expense_mark_reimbursed'),

    # P & L (admin-only)
    path('pnl/', views.pnl_view, name='pnl_view'),

    # Invoices
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<int:pk>/regenerate/', views.invoice_regenerate, name='invoice_regenerate'),
]
