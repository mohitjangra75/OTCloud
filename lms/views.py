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
    queryset = Lead.active_objects.select_related('assigned_to').all()

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
    lead = get_object_or_404(
        Lead.active_objects.select_related('assigned_to', 'converted_client'),
        pk=pk,
    )
    follow_ups = lead.follow_ups.filter(is_deleted=False).order_by('-follow_up_date')
    follow_up_form = FollowUpForm()

    return render(request, 'lms/lead_detail.html', {
        'lead': lead,
        'follow_ups': follow_ups,
        'follow_up_form': follow_up_form,
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
def lead_convert(request, pk):
    lead = get_object_or_404(Lead.active_objects, pk=pk)

    if request.method == 'POST':
        try:
            client = LeadService.convert_to_client(lead.pk, converted_by=request.user)
            messages.success(
                request,
                f'Lead "{lead.name}" converted to client "{client.full_name}".',
            )
        except ValueError as e:
            messages.error(request, str(e))

    return redirect('lms:lead_detail', pk=lead.pk)


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
