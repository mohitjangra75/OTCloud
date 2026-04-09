from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from billing.forms import InvoiceForm, InvoiceItemForm
from billing.models import Invoice
from billing.services import BillingService
from clients.models import Client


def _get_client_for_user(user):
    """Find the Client record for a user - by linked user FK or by mobile number."""
    # First try direct link
    try:
        return user.client_profile
    except Client.DoesNotExist:
        pass
    # Fallback: match by mobile number
    return Client.active_objects.filter(mobile_number=user.mobile_number).first()


def _staff_required(view_func):
    """Decorator that restricts access to admin and staff users."""
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_admin or request.user.is_therapist):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('billing:invoice_list')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    wrapper.__doc__ = view_func.__doc__
    return wrapper


@login_required
def invoice_list(request):
    queryset = Invoice.active_objects.select_related('client').all()

    # Clients can only see their own invoices
    if request.user.role == 'client':
        client = _get_client_for_user(request.user)
        if client:
            queryset = queryset.filter(client=client)
        else:
            queryset = queryset.none()

    status_filter = request.GET.get('status')
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    client_filter = request.GET.get('client')
    if client_filter:
        queryset = queryset.filter(client_id=client_filter)

    paginator = Paginator(queryset, 20)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'billing/invoice_list.html', {
        'page_obj': page,
        'status_choices': Invoice.Status.choices,
        'current_status': status_filter or '',
        'is_client': request.user.role == 'client',
    })


@login_required
@_staff_required
def invoice_create(request):
    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        if form.is_valid():
            invoice = BillingService.create_invoice(
                client=form.cleaned_data['client'],
                due_date=form.cleaned_data.get('due_date'),
                notes=form.cleaned_data.get('notes', ''),
                created_by=request.user,
            )
            messages.success(request, f'Invoice {invoice.invoice_number} created.')
            return redirect('billing:invoice_detail', pk=invoice.pk)
    else:
        form = InvoiceForm()

    return render(request, 'billing/invoice_form.html', {
        'form': form,
        'title': 'Create Invoice',
    })


@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(
        Invoice.active_objects.select_related('client').prefetch_related('items'),
        pk=pk,
    )

    # Clients can only view their own invoices
    if request.user.role == 'client':
        client = _get_client_for_user(request.user)
        if not client or invoice.client != client:
            messages.error(request, 'You do not have permission to view this invoice.')
            return redirect('billing:invoice_list')

    item_form = InvoiceItemForm() if request.user.role != 'client' else None

    return render(request, 'billing/invoice_detail.html', {
        'invoice': invoice,
        'item_form': item_form,
        'is_client': request.user.role == 'client',
    })


@login_required
@_staff_required
def invoice_update(request, pk):
    invoice = get_object_or_404(Invoice.active_objects, pk=pk)

    if request.method == 'POST':
        form = InvoiceForm(request.POST, instance=invoice)
        if form.is_valid():
            inv = form.save(commit=False)
            inv.updated_by = request.user
            inv.save()
            messages.success(request, 'Invoice updated.')
            return redirect('billing:invoice_detail', pk=inv.pk)
    else:
        form = InvoiceForm(instance=invoice)

    return render(request, 'billing/invoice_form.html', {
        'form': form,
        'title': 'Edit Invoice',
        'invoice': invoice,
    })


@login_required
@_staff_required
def invoice_delete(request, pk):
    invoice = get_object_or_404(Invoice.active_objects, pk=pk)

    if request.method == 'POST':
        invoice.soft_delete()
        messages.success(request, f'Invoice {invoice.invoice_number} deleted.')
        return redirect('billing:invoice_list')

    return render(request, 'billing/invoice_confirm_delete.html', {
        'invoice': invoice,
    })


@login_required
@_staff_required
def invoice_add_item(request, pk):
    invoice = get_object_or_404(Invoice.active_objects, pk=pk)

    if request.method == 'POST':
        form = InvoiceItemForm(request.POST)
        if form.is_valid():
            BillingService.add_item(
                invoice=invoice,
                date=form.cleaned_data['date'],
                description=form.cleaned_data['description'],
                amount=form.cleaned_data['amount'],
                appointment=form.cleaned_data.get('appointment'),
                created_by=request.user,
            )
            messages.success(request, 'Item added to invoice.')
        else:
            messages.error(request, 'Failed to add item. Please check the form.')

    return redirect('billing:invoice_detail', pk=invoice.pk)


@login_required
@_staff_required
def invoice_mark_paid(request, pk):
    invoice = get_object_or_404(Invoice.active_objects, pk=pk)

    if request.method == 'POST':
        try:
            amount = invoice.balance_due
            raw_amount = request.POST.get('amount', '').strip()
            if raw_amount:
                amount = abs(float(raw_amount))
            BillingService.mark_paid(invoice.pk, amount)
            messages.success(request, 'Invoice marked as paid.')
        except (ValueError, TypeError):
            messages.error(request, 'Invalid payment amount.')

    return redirect('billing:invoice_detail', pk=invoice.pk)
