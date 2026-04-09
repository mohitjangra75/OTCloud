from django.urls import path
from billing import views

app_name = 'billing'

urlpatterns = [
    path('', views.invoice_list, name='invoice_list'),
    path('create/', views.invoice_create, name='invoice_create'),
    path('<uuid:pk>/', views.invoice_detail, name='invoice_detail'),
    path('<uuid:pk>/edit/', views.invoice_update, name='invoice_update'),
    path('<uuid:pk>/delete/', views.invoice_delete, name='invoice_delete'),
    path('<uuid:pk>/add-item/', views.invoice_add_item, name='invoice_add_item'),
    path('<uuid:pk>/mark-paid/', views.invoice_mark_paid, name='invoice_mark_paid'),
]
