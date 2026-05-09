from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from lms.forms import LeadForm, FollowUpForm
from lms.models import Lead, FollowUp
from lms.services import LeadService


def _staff_required(view_func):
    """Decorator that restricts access to admin and staff users."""
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_admin or request.user.is_therapist):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('lms:lead_list')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    wrapper.__doc__ = view_func.__doc__
    return wrapper


@login_required
@_staff_required
def lead_list(request):
    queryset = Lead.active_objects.all()

    status_filter = request.GET.get('status')
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    source_filter = request.GET.get('source')
    if source_filter:
        queryset = queryset.filter(source=source_filter)

    search = request.GET.get('q', '').strip()
    if search:
        queryset = queryset.filter(name__icontains=search)

    paginator = Paginator(queryset, 20)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'lms/lead_list.html', {
        'page_obj': page,
        'status_choices': Lead.Status.choices,
        'source_choices': Lead.Source.choices,
        'current_status': status_filter or '',
        'current_source': source_filter or '',
        'search_query': search,
    })


@login_required
@_staff_required
def lead_create(request):
    if request.method == 'POST':
        form = LeadForm(request.POST)
        if form.is_valid():
            lead = LeadService.create_lead(
                data=form.cleaned_data,
                created_by=request.user,
            )
            messages.success(request, f'Lead "{lead.name}" created.')
            return redirect('lms:lead_detail', pk=lead.pk)
    else:
        form = LeadForm()

    return render(request, 'lms/lead_form.html', {
        'form': form,
        'title': 'Add Lead',
    })


@login_required
@_staff_required
def lead_detail(request, pk):
    from django.utils import timezone
    lead = get_object_or_404(
        Lead.active_objects.select_related('converted_client'),
        pk=pk,
    )
    follow_ups = lead.follow_ups.filter(is_deleted=False).order_by('-follow_up_date')
    follow_up_form = FollowUpForm()

    pending_count = follow_ups.filter(status='pending').count()
    completed_count = follow_ups.filter(status='completed').count()
    missed_count = follow_ups.filter(status='missed').count()
    last_completed = follow_ups.filter(status='completed').order_by('-follow_up_date').first()
    next_pending = follow_ups.filter(status='pending').order_by('follow_up_date').first()
    age_days = (timezone.now().date() - lead.created_at.date()).days

    # Split follow-ups into upcoming/overdue (pending) and done (completed/missed),
    # tagging each with an urgency label for nicer per-row styling.
    today = timezone.now().date()
    upcoming, done = [], []
    for fu in follow_ups:
        delta = (fu.follow_up_date.date() - today).days
        if fu.status == 'pending':
            if delta < 0:
                urgency = 'overdue'; rel = f"Overdue {-delta}d"
            elif delta == 0:
                urgency = 'today'; rel = "Today"
            elif delta == 1:
                urgency = 'tomorrow'; rel = "Tomorrow"
            elif delta <= 7:
                urgency = 'soon'; rel = f"In {delta}d"
            else:
                urgency = 'future'; rel = f"In {delta}d"
            upcoming.append({'fu': fu, 'urgency': urgency, 'rel': rel})
        else:
            if delta < 0:
                rel = f"{-delta}d ago"
            elif delta == 0:
                rel = "Today"
            else:
                rel = fu.follow_up_date.strftime('%d %b')
            done.append({'fu': fu, 'urgency': fu.status, 'rel': rel})
    upcoming.sort(key=lambda x: x['fu'].follow_up_date)
    done.sort(key=lambda x: x['fu'].follow_up_date, reverse=True)

    journey_stages = ['new', 'contacted', 'interested', 'converted']
    if lead.status == 'lost':
        current_idx = -1  # special branch
    elif lead.status in journey_stages:
        current_idx = journey_stages.index(lead.status)
    else:
        current_idx = 0

    return render(request, 'lms/lead_detail.html', {
        'lead': lead,
        'follow_ups': follow_ups,
        'upcoming_follow_ups': upcoming,
        'done_follow_ups': done,
        'follow_up_form': follow_up_form,
        'pending_count': pending_count,
        'completed_count': completed_count,
        'missed_count': missed_count,
        'last_completed': last_completed,
        'next_pending': next_pending,
        'age_days': age_days,
        'journey_stages': journey_stages,
        'current_idx': current_idx,
    })


@login_required
@_staff_required
def lead_update(request, pk):
    lead = get_object_or_404(Lead.active_objects, pk=pk)

    if request.method == 'POST':
        form = LeadForm(request.POST, instance=lead)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.updated_by = request.user
            obj.save()
            messages.success(request, 'Lead updated.')
            return redirect('lms:lead_detail', pk=obj.pk)
    else:
        form = LeadForm(instance=lead)

    return render(request, 'lms/lead_form.html', {
        'form': form,
        'title': 'Edit Lead',
        'lead': lead,
    })


@login_required
@_staff_required
def lead_delete(request, pk):
    lead = get_object_or_404(Lead.active_objects, pk=pk)

    if request.method == 'POST':
        lead.soft_delete()
        messages.success(request, f'Lead "{lead.name}" deleted.')
        return redirect('lms:lead_list')

    return render(request, 'lms/lead_confirm_delete.html', {
        'lead': lead,
    })


@login_required
@_staff_required
def lead_add_follow_up(request, pk):
    lead = get_object_or_404(Lead.active_objects, pk=pk)

    if request.method == 'POST':
        form = FollowUpForm(request.POST)
        if form.is_valid():
            LeadService.add_follow_up(
                lead_id=lead.pk,
                follow_up_date=form.cleaned_data['follow_up_date'],
                notes=form.cleaned_data.get('notes', ''),
                created_by=request.user,
            )
            messages.success(request, 'Follow-up scheduled.')
        else:
            messages.error(request, 'Failed to schedule follow-up. Please check the form.')

    return redirect('lms:lead_detail', pk=lead.pk)


@login_required
@_staff_required
def lead_status_change(request, pk):
    """Inline status change from the leads list — POST-only."""
    lead = get_object_or_404(Lead.active_objects, pk=pk)
    if request.method != 'POST':
        return redirect('lms:lead_list')

    new_status = (request.POST.get('status') or '').strip()
    try:
        LeadService.update_status(lead.pk, new_status, actor=request.user)
        messages.success(request, f'{lead.name} → {dict(Lead.Status.choices).get(new_status, new_status)}.')
    except (ValueError, Lead.DoesNotExist) as e:
        messages.error(request, str(e))

    redirect_to = request.POST.get('next') or 'lms:lead_list'
    if redirect_to.startswith('/'):
        from django.utils.http import url_has_allowed_host_and_scheme
        if url_has_allowed_host_and_scheme(redirect_to, allowed_hosts={request.get_host()}):
            return redirect(redirect_to)
    return redirect('lms:lead_list')


@login_required
@_staff_required
def lead_to_appointment(request, pk):
    """Send the user to the appointment-create form, prefilled from the lead."""
    lead = get_object_or_404(Lead.active_objects, pk=pk)
    # Carry the lead's name + mobile + lead_id so the appointment view can pre-fill,
    # and so we can mark the lead as CONVERTED once the appointment is saved.
    from urllib.parse import urlencode
    qs = urlencode({
        'lead_id': lead.pk,
        'client_name': lead.name,
        'client_mobile': lead.mobile,
    })
    return redirect(f"/appointments/create/?{qs}")


@login_required
@_staff_required
def follow_up_list(request):
    queryset = (
        FollowUp.active_objects
        .select_related('lead')
        .order_by('follow_up_date')
    )

    status_filter = request.GET.get('status')
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    paginator = Paginator(queryset, 20)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'lms/follow_up_list.html', {
        'page_obj': page,
        'current_status': status_filter or '',
    })


@login_required
@_staff_required
def follow_up_mark_completed(request, pk):
    follow_up = get_object_or_404(FollowUp.active_objects, pk=pk)

    if request.method == 'POST':
        follow_up.status = 'completed'
        follow_up.updated_by = request.user
        follow_up.save(update_fields=['status', 'updated_by', 'updated_at'])
        messages.success(request, 'Follow-up marked as completed.')

    return redirect('lms:lead_detail', pk=follow_up.lead_id)
