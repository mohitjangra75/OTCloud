from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from billing.forms import BillPaymentForm, ExpenseForm, MonthlyBillForm
from billing.models import Expense, Invoice, MonthlyBill
from billing.services import (
    BillingService,
    BillingServiceError,
    ExpenseService,
    InvoiceService,
    PnLService,
    first_of_month,
    next_month,
    previous_month,
)
from clients.models import Client


def _get_client_for_user(user):
    try:
        return user.client_profile
    except Client.DoesNotExist:
        pass
    return Client.active_objects.filter(mobile_number=user.mobile_number).first()


def _admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_admin:
            messages.error(request, 'Only admins can perform this action.')
            return redirect('billing:monthly_view')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    wrapper.__doc__ = view_func.__doc__
    return wrapper


def _parse_month(raw, fallback=None):
    fallback = fallback or first_of_month(date.today())
    if not raw:
        return fallback
    raw = raw.strip()
    for fmt_len, fmt in ((7, '%Y-%m'), (10, '%Y-%m-%d')):
        if len(raw) >= fmt_len:
            try:
                return first_of_month(date.fromisoformat(raw[:10] if fmt_len == 10 else raw[:7] + '-01'))
            except ValueError:
                continue
    try:
        return first_of_month(date.fromisoformat(raw))
    except ValueError:
        return fallback


# ============================================================
#  MONTHLY BILLING (replaces invoices)
# ============================================================


@login_required
def monthly_view(request):
    """Spreadsheet-style monthly ledger of client billing rows."""
    from appointments.models import TherapyType

    today = date.today()
    month = _parse_month(request.GET.get('month'), first_of_month(today))
    client_id = request.GET.get('client') or ''

    bills = BillingService.get_month_bills(month, client_id=client_id or None)

    # Client-side filter: clients can only see their own
    if request.user.role == 'client':
        client = _get_client_for_user(request.user)
        bills = bills.filter(client=client) if client else bills.none()

    summary = BillingService.month_summary(month)

    # Group bills by client for visual grouping (like the sheet)
    grouped = []
    current_client = None
    current_rows = []
    for b in bills:
        if current_client is None or b.client_id != current_client.id:
            if current_client is not None:
                grouped.append({
                    'client': current_client,
                    'rows': current_rows,
                    'band': len(grouped) % 6,
                })
            current_client = b.client
            current_rows = []
        current_rows.append(b)
    if current_client is not None:
        grouped.append({
            'client': current_client,
            'rows': current_rows,
            'band': len(grouped) % 6,
        })

    all_clients = (Client.active_objects.order_by('first_name', 'last_name')
                   if request.user.is_admin else Client.active_objects.none())
    therapy_types = TherapyType.active_objects.order_by('name')

    return render(request, 'billing/monthly_view.html', {
        'month': month,
        'month_label': month.strftime('%B %Y'),
        'prev_month': previous_month(month).isoformat()[:7],
        'next_month': next_month(month).isoformat()[:7],
        'grouped_bills': grouped,
        'summary': summary,
        'is_client': request.user.role == 'client',
        'is_admin': request.user.is_admin,
        'all_clients': all_clients,
        'therapy_types': therapy_types,
        'client_filter': client_id,
        'payment_modes': [
            ('cash', 'Cash'), ('upi', 'UPI'), ('bank', 'Bank'),
            ('card', 'Card'), ('cheque', 'Cheque'), ('other', 'Other'),
        ],
        'today_iso': today.isoformat(),
    })


@login_required
@_admin_required
def bill_inline_create(request):
    """Inline Excel-style add — single POST creates a row from the table footer."""
    if request.method != 'POST':
        return redirect('billing:monthly_view')

    try:
        client = Client.active_objects.get(pk=request.POST.get('client'))
        from appointments.models import TherapyType
        therapy = TherapyType.active_objects.get(pk=request.POST.get('therapy_type'))
    except (Client.DoesNotExist, ValueError, TypeError):
        messages.error(request, 'Pick a valid client and session type.')
        return redirect(f"/billing/?month={request.POST.get('month_redirect', '')}")
    except Exception:
        messages.error(request, 'Invalid input.')
        return redirect('billing:monthly_view')

    raw_month = (request.POST.get('month') or '').strip()
    month = _parse_month(raw_month, first_of_month(date.today()))

    def _num(name, default=0):
        v = (request.POST.get(name) or '').strip()
        if not v:
            return default
        try:
            return float(v)
        except ValueError:
            return default

    paid_date = None
    raw_paid = (request.POST.get('paid_date') or '').strip()
    if raw_paid:
        try:
            paid_date = date.fromisoformat(raw_paid)
        except ValueError:
            paid_date = None

    try:
        BillingService.create_or_update_bill(
            client=client,
            therapy_type=therapy,
            month=month,
            sessions_per_week=int(_num('sessions_per_week') or 0),
            total_sessions=int(_num('total_sessions') or 0),
            package_amount=_num('package_amount'),
            paid_amount=_num('paid_amount'),
            carry_forward=_num('carry_forward', None) if (request.POST.get('carry_forward') or '').strip() else None,
            payment_mode=request.POST.get('payment_mode') or '',
            paid_date=paid_date,
            notes=request.POST.get('notes') or '',
            actor=request.user,
        )
        messages.success(request, 'Row added.')
    except BillingServiceError as e:
        messages.error(request, str(e))

    return redirect(f"/billing/?month={month.strftime('%Y-%m')}")


@login_required
@_admin_required
def bill_create(request):
    initial_month = _parse_month(request.GET.get('month'))
    if request.method == 'POST':
        form = MonthlyBillForm(request.POST)
        if form.is_valid():
            try:
                bill = BillingService.create_or_update_bill(
                    client=form.cleaned_data['client'],
                    therapy_type=form.cleaned_data['therapy_type'],
                    month=form.cleaned_data['month'],
                    sessions_per_week=form.cleaned_data.get('sessions_per_week') or 0,
                    total_sessions=form.cleaned_data.get('total_sessions') or 0,
                    package_amount=form.cleaned_data.get('package_amount') or 0,
                    paid_amount=form.cleaned_data.get('paid_amount') or 0,
                    carry_forward=form.cleaned_data.get('carry_forward'),
                    payment_mode=form.cleaned_data.get('payment_mode') or '',
                    paid_date=form.cleaned_data.get('paid_date'),
                    notes=form.cleaned_data.get('notes') or '',
                    actor=request.user,
                )
                messages.success(request, f'Saved billing for {bill.client} ({bill.therapy_type}).')
                return redirect(f"{request.build_absolute_uri('/').rstrip('/')}/billing/?month={bill.month.strftime('%Y-%m')}")
            except BillingServiceError as e:
                messages.error(request, str(e))
    else:
        form = MonthlyBillForm(initial={'month': initial_month})

    return render(request, 'billing/bill_form.html', {
        'form': form, 'title': 'Add Monthly Billing',
    })


@login_required
@_admin_required
def bill_update(request, pk):
    bill = get_object_or_404(MonthlyBill.active_objects, pk=pk)
    if request.method == 'POST':
        form = MonthlyBillForm(request.POST, instance=bill)
        if form.is_valid():
            try:
                BillingService.create_or_update_bill(
                    client=form.cleaned_data['client'],
                    therapy_type=form.cleaned_data['therapy_type'],
                    month=form.cleaned_data['month'],
                    sessions_per_week=form.cleaned_data.get('sessions_per_week') or 0,
                    total_sessions=form.cleaned_data.get('total_sessions') or 0,
                    package_amount=form.cleaned_data.get('package_amount') or 0,
                    paid_amount=form.cleaned_data.get('paid_amount') or 0,
                    carry_forward=form.cleaned_data.get('carry_forward'),
                    payment_mode=form.cleaned_data.get('payment_mode') or '',
                    paid_date=form.cleaned_data.get('paid_date'),
                    notes=form.cleaned_data.get('notes') or '',
                    actor=request.user,
                )
                messages.success(request, 'Bill updated.')
                return redirect(f"/billing/?month={form.cleaned_data['month'].strftime('%Y-%m')}")
            except BillingServiceError as e:
                messages.error(request, str(e))
    else:
        form = MonthlyBillForm(instance=bill)
    return render(request, 'billing/bill_form.html', {
        'form': form, 'title': 'Edit Monthly Billing', 'bill': bill,
    })


@login_required
@_admin_required
def bill_record_payment(request, pk):
    bill = get_object_or_404(MonthlyBill.active_objects, pk=pk)
    if request.method == 'POST':
        form = BillPaymentForm(request.POST)
        if form.is_valid():
            try:
                BillingService.record_payment(
                    bill_id=bill.pk,
                    amount=form.cleaned_data['amount'],
                    mode=form.cleaned_data.get('payment_mode') or '',
                    paid_date=form.cleaned_data.get('paid_date'),
                    actor=request.user,
                )
                messages.success(request, 'Payment recorded.')
            except BillingServiceError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, 'Invalid payment details.')
    return redirect(f"/billing/?month={bill.month.strftime('%Y-%m')}")


@login_required
@_admin_required
def bill_delete(request, pk):
    bill = get_object_or_404(MonthlyBill.active_objects, pk=pk)
    month_str = bill.month.strftime('%Y-%m')
    if request.method == 'POST':
        bill.soft_delete()
        messages.success(request, 'Billing row deleted.')
    return redirect(f"/billing/?month={month_str}")


# ============================================================
#  EXPENSES & REIMBURSEMENTS
# ============================================================


@login_required
def expense_view(request):
    from accounts.models import User
    from django.db.models import Sum
    today = date.today()
    month = _parse_month(request.GET.get('month'), first_of_month(today))

    if request.user.role == 'client':
        messages.error(request, 'No access.')
        return redirect('billing:monthly_view')

    is_admin = request.user.is_admin

    qs = ExpenseService.get_month_expenses(month)
    if not is_admin:
        # Staff see only their own submissions
        qs = qs.filter(paid_to_employee=request.user)

    pending = qs.exclude(status=Expense.Status.REIMBURSED).order_by('date', 'id')
    paid = qs.filter(status=Expense.Status.REIMBURSED).order_by('-date', '-id')

    pending_total = pending.aggregate(t=Sum('amount'))['t'] or 0
    paid_total = paid.aggregate(t=Sum('amount'))['t'] or 0
    grand_total = (pending_total or 0) + (paid_total or 0)

    employees = User.objects.filter(
        role__in=['staff', 'admin'], is_active=True,
    ).order_by('first_name', 'last_name')

    return render(request, 'billing/expense_view.html', {
        'month': month,
        'month_label': month.strftime('%B %Y'),
        'prev_month': previous_month(month).isoformat()[:7],
        'next_month': next_month(month).isoformat()[:7],
        'pending_rows': pending,
        'paid_rows': paid,
        'pending_total': pending_total,
        'paid_total': paid_total,
        'grand_total': grand_total,
        'is_admin': is_admin,
        'employees': employees,
        'today_iso': today.isoformat(),
        'payment_modes': [
            ('cash', 'Cash'), ('upi', 'UPI'), ('bank', 'Bank'),
            ('card', 'Card'), ('cheque', 'Cheque'), ('other', 'Other'),
        ],
    })


@login_required
def expense_inline_create(request):
    """Inline add — every entry is a reimbursement-style claim. Submitter pays;
    admin marks as paid back."""
    from accounts.models import User
    if request.method != 'POST':
        return redirect('billing:expense_view')

    if request.user.role == 'client':
        messages.error(request, 'No access.')
        return redirect('billing:monthly_view')

    raw_date = (request.POST.get('date') or '').strip()
    try:
        d = date.fromisoformat(raw_date) if raw_date else date.today()
    except ValueError:
        d = date.today()

    item = (request.POST.get('item') or '').strip()
    if not item:
        messages.error(request, 'Item is required.')
        return redirect(f"/billing/expenses/?month={d.strftime('%Y-%m')}")

    raw_amt = (request.POST.get('amount') or '').strip()
    try:
        amount = float(raw_amt)
    except ValueError:
        messages.error(request, 'Amount is required.')
        return redirect(f"/billing/expenses/?month={d.strftime('%Y-%m')}")

    # Resolve which employee this is for. Staff submit for themselves; admin
    # may submit on behalf of any employee.
    if request.user.is_admin:
        emp_id = request.POST.get('paid_to_employee') or ''
        try:
            paid_to_employee = User.objects.get(pk=int(emp_id)) if emp_id else None
        except (User.DoesNotExist, ValueError):
            paid_to_employee = None
    else:
        paid_to_employee = request.user

    ExpenseService.create_expense(
        date_=d, item=item, amount=amount,
        category=Expense.Category.REIMBURSEMENT,
        remarks=request.POST.get('remarks') or '',
        payment_mode=request.POST.get('payment_mode') or '',
        paid_to='',
        paid_to_employee=paid_to_employee,
        paid_by=request.user,
        status=Expense.Status.PENDING,
        actor=request.user,
    )
    messages.success(request, 'Entry added.')
    return redirect(f"/billing/expenses/?month={d.strftime('%Y-%m')}")


@login_required
def expense_create(request):
    if request.user.role == 'client':
        messages.error(request, 'No access.')
        return redirect('billing:monthly_view')

    initial = {'date': date.today()}
    if not request.user.is_admin:
        # Staff submits a reimbursement for self
        initial.update({
            'category': Expense.Category.REIMBURSEMENT,
            'paid_to_employee': request.user,
        })

    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            category = cd['category']
            if not request.user.is_admin:
                # Staff cannot create org expenses; force reimbursement to self
                category = Expense.Category.REIMBURSEMENT
                paid_to_employee = request.user
                status = Expense.Status.PENDING
            else:
                paid_to_employee = cd.get('paid_to_employee')
                status = cd.get('status') or (
                    Expense.Status.PENDING if category == Expense.Category.REIMBURSEMENT
                    else Expense.Status.APPROVED
                )

            ExpenseService.create_expense(
                date_=cd['date'], item=cd['item'],
                amount=cd['amount'], category=category,
                remarks=cd.get('remarks') or '',
                payment_mode=cd.get('payment_mode') or '',
                paid_to=cd.get('paid_to') or '',
                paid_to_employee=paid_to_employee,
                paid_by=request.user,
                status=status,
                actor=request.user,
            )
            messages.success(request, 'Expense recorded.')
            return redirect(f"/billing/expenses/?month={cd['date'].strftime('%Y-%m')}")
    else:
        form = ExpenseForm(initial=initial)

    if not request.user.is_admin:
        # Hide org-only fields from staff-side form
        for f in ('category', 'paid_to', 'paid_to_employee', 'status'):
            if f in form.fields:
                form.fields[f].widget = form.fields[f].hidden_widget()

    return render(request, 'billing/expense_form.html', {
        'form': form, 'title': 'New Expense',
        'is_admin': request.user.is_admin,
    })


@login_required
@_admin_required
def expense_update(request, pk):
    expense = get_object_or_404(Expense.active_objects, pk=pk)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.updated_by = request.user
            obj.save()
            messages.success(request, 'Expense updated.')
            return redirect(f"/billing/expenses/?month={obj.date.strftime('%Y-%m')}")
    else:
        form = ExpenseForm(instance=expense)
    return render(request, 'billing/expense_form.html', {
        'form': form, 'title': 'Edit Expense',
        'expense': expense, 'is_admin': True,
    })


@login_required
@_admin_required
def expense_delete(request, pk):
    expense = get_object_or_404(Expense.active_objects, pk=pk)
    month_str = expense.date.strftime('%Y-%m')
    if request.method == 'POST':
        expense.soft_delete()
        messages.success(request, 'Expense deleted.')
    return redirect(f"/billing/expenses/?month={month_str}")


# ============================================================
#  INVOICES (auto-generated from MonthlyBill)
# ============================================================


@login_required
def invoice_list(request):
    """One invoice per (client, month). Admin sees all; client sees own."""
    today = date.today()
    month_filter = request.GET.get('month') or ''
    month = _parse_month(month_filter, None) if month_filter else None

    qs = InvoiceService.get_invoices(month=month)

    if request.user.role == 'client':
        client = _get_client_for_user(request.user)
        qs = qs.filter(client=client) if client else qs.none()

    return render(request, 'billing/invoice_list.html', {
        'invoices': qs[:500],
        'month_filter': month.strftime('%Y-%m') if month else '',
        'is_admin': request.user.is_admin,
        'is_client': request.user.role == 'client',
    })


@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(
        Invoice.active_objects.select_related('client'), pk=pk,
    )
    if request.user.role == 'client':
        client = _get_client_for_user(request.user)
        if not client or invoice.client_id != client.id:
            messages.error(request, 'You cannot view this invoice.')
            return redirect('billing:invoice_list')

    # Refresh totals so the displayed numbers always match current MonthlyBill data
    refreshed = InvoiceService.regenerate_for_client_month(
        client=invoice.client, target_date=invoice.month, actor=request.user,
    )
    if refreshed is not None:
        invoice = refreshed

    invoice, lines = InvoiceService.get_invoice_with_lines(invoice)

    return render(request, 'billing/invoice_detail.html', {
        'invoice': invoice,
        'lines': lines,
        'is_admin': request.user.is_admin,
        'is_client': request.user.role == 'client',
    })


@login_required
@_admin_required
def invoice_regenerate(request, pk):
    invoice = get_object_or_404(Invoice.active_objects, pk=pk)
    if request.method == 'POST':
        InvoiceService.regenerate_for_client_month(
            client=invoice.client, target_date=invoice.month, actor=request.user,
        )
        messages.success(request, 'Invoice regenerated.')
    return redirect('billing:invoice_detail', pk=invoice.pk)


# ============================================================
#  P & L (admin-only)
# ============================================================


@login_required
@_admin_required
def pnl_view(request):
    today = date.today()
    month = _parse_month(request.GET.get('month'), first_of_month(today))
    try:
        year = int(request.GET.get('year') or month.year)
    except (TypeError, ValueError):
        year = month.year

    monthly = PnLService.month(month)
    yearly = PnLService.year(year)

    def _margin(income, profit):
        try:
            i = float(income or 0)
            return round((float(profit or 0) / i) * 100, 1) if i else 0.0
        except Exception:
            return 0.0
    monthly_margin = _margin(monthly['total_income'], monthly['profit_loss'])
    yearly_margin = _margin(yearly['total_income'], yearly['profit_loss'])
    yearly_avg_per_session = (
        round(float(yearly['total_income']) / yearly['session_count'])
        if yearly['session_count'] else 0
    )

    # Hand a plain dict — the {% json_script %} tag will serialize it once
    chart_data = {
        'monthLabels': [m['start'].strftime('%b') for m in yearly['months']],
        'incomeSeries': [float(m['total_income']) for m in yearly['months']],
        'expenseSeries': [float(m['total_expenses']) for m in yearly['months']],
        'profitSeries': [float(m['profit_loss']) for m in yearly['months']],
    }

    return render(request, 'billing/pnl.html', {
        'month': month,
        'monthly': monthly,
        'monthly_margin': monthly_margin,
        'prev_month': previous_month(month).isoformat()[:7],
        'next_month': next_month(month).isoformat()[:7],
        'yearly': yearly,
        'yearly_margin': yearly_margin,
        'yearly_avg_per_session': yearly_avg_per_session,
        'year_value': year,
        'prev_year': year - 1,
        'next_year': year + 1,
        'chart_data': chart_data,
    })


@login_required
@_admin_required
def expense_mark_reimbursed(request, pk):
    expense = get_object_or_404(Expense.active_objects, pk=pk)
    if request.method == 'POST':
        expense.status = Expense.Status.REIMBURSED
        expense.updated_by = request.user
        expense.save(update_fields=['status', 'updated_by', 'updated_at'])
        messages.success(request, 'Marked as reimbursed.')
    return redirect(f"/billing/expenses/?month={expense.date.strftime('%Y-%m')}")
