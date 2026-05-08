from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import User
from salary.forms import SalarySettingForm
from salary.models import MonthlySalary, SalarySetting
from salary.services import (
    SalaryService,
    first_of_month,
    next_month,
    previous_month,
)


def _admin_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_admin:
            messages.error(request, 'Only admins can access this page.')
            return redirect('salary:my_salary')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    wrapper.__doc__ = view_func.__doc__
    return wrapper


def _parse_month(raw, fallback=None):
    fallback = fallback or first_of_month(date.today())
    if not raw:
        return fallback
    raw = raw.strip()[:10]
    try:
        if len(raw) == 7:
            return first_of_month(date.fromisoformat(raw + '-01'))
        return first_of_month(date.fromisoformat(raw))
    except ValueError:
        return fallback


@login_required
@_admin_required
def salary_list(request):
    """Admin view: month picker + table of all staff salaries (auto-recompute)."""
    today = date.today()
    month = _parse_month(request.GET.get('month'), first_of_month(today))

    # Auto recompute on view
    SalaryService.compute_all(month, actor=request.user)

    rows = SalaryService.get_month(month)

    # Aggregates
    agg = rows.aggregate(
        salary=Sum('base_monthly_salary'),
        deduction=Sum('deduction'),
        incentive=Sum('incentive'),
        in_hand=Sum('in_hand_salary'),
        sessions=Sum('total_sessions'),
        extra=Sum('extra_sessions'),
    )
    summary = {
        'employees': rows.count(),
        'salary': agg['salary'] or Decimal('0'),
        'deduction': agg['deduction'] or Decimal('0'),
        'incentive': agg['incentive'] or Decimal('0'),
        'in_hand': agg['in_hand'] or Decimal('0'),
        'sessions': agg['sessions'] or 0,
        'extra_sessions': agg['extra'] or 0,
    }

    return render(request, 'salary/salary_list.html', {
        'month': month,
        'month_label': month.strftime('%B %Y'),
        'prev_month': previous_month(month).isoformat()[:7],
        'next_month': next_month(month).isoformat()[:7],
        'rows': rows,
        'summary': summary,
        'today_iso': today.isoformat(),
    })


@login_required
def my_salary(request):
    """Each employee can view their own current-month salary breakdown."""
    if request.user.role == 'client':
        messages.error(request, 'No access.')
        return redirect('analytics:dashboard')

    today = date.today()
    month = _parse_month(request.GET.get('month'), first_of_month(today))

    snap = SalaryService.compute(request.user, month, actor=request.user)

    # Build a 6-month history for the employee
    history = []
    cur = month
    for _ in range(6):
        h = MonthlySalary.active_objects.filter(employee=request.user, month=cur).first()
        if h is None and cur <= first_of_month(today):
            h = SalaryService.compute(request.user, cur, actor=request.user)
        if h:
            history.append(h)
        cur = previous_month(cur)
    history.reverse()

    return render(request, 'salary/my_salary.html', {
        'snap': snap,
        'month': month,
        'month_label': month.strftime('%B %Y'),
        'prev_month': previous_month(month).isoformat()[:7],
        'next_month': next_month(month).isoformat()[:7],
        'history': history,
    })


@login_required
@_admin_required
def settings_edit(request, employee_id):
    employee = get_object_or_404(User, pk=employee_id, role__in=[User.Role.STAFF, User.Role.ADMIN])
    setting, _ = SalarySetting.objects.get_or_create(
        employee=employee, defaults={'created_by': request.user},
    )
    if request.method == 'POST':
        form = SalarySettingForm(request.POST, instance=setting)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.updated_by = request.user
            obj.is_deleted = False
            obj.save()
            messages.success(request, f'Salary rules saved for {employee.get_full_name() or employee.mobile_number}.')
            return redirect('salary:salary_list')
    else:
        form = SalarySettingForm(instance=setting)
    return render(request, 'salary/settings_form.html', {
        'form': form, 'employee': employee, 'setting': setting,
    })
