from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View

from clients.forms import ClientForm
from clients.models import Client
from clients.services import ClientService, ClientServiceError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _admin_or_staff_required(view_func):
    """Allow only admin or staff role users."""
    from functools import wraps

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not (user.is_superuser or user.role in ('admin', 'staff')):
            messages.error(request, "You do not have permission to manage clients.")
            return redirect('/')
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@method_decorator([login_required, _admin_or_staff_required], name='dispatch')
class ClientListView(View):
    template_name = 'clients/client_list.html'
    paginate_by = 20

    def get(self, request):
        query = request.GET.get('q', '').strip()
        if query:
            clients = ClientService.search_clients(query)
        else:
            clients = ClientService.get_all_clients()

        paginator = Paginator(clients, self.paginate_by)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context = {
            'page_obj': page_obj,
            'clients': page_obj,
            'search_query': query,
        }
        return render(request, self.template_name, context)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

@method_decorator([login_required, _admin_or_staff_required], name='dispatch')
class ClientDetailView(View):
    template_name = 'clients/client_detail.html'

    def get(self, request, pk):
        try:
            client = ClientService.get_client(pk)
        except ClientServiceError:
            messages.error(request, "Client not found.")
            return redirect('clients:client_list')

        session_count = ClientService.get_session_count(pk)

        context = {
            'client': client,
            'session_count': session_count,
        }
        return render(request, self.template_name, context)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@method_decorator([login_required, _admin_or_staff_required], name='dispatch')
class ClientCreateView(View):
    template_name = 'clients/client_form.html'

    def get(self, request):
        form = ClientForm()
        return render(request, self.template_name, {'form': form, 'action': 'Create'})

    def post(self, request):
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            client.created_by = request.user
            client.save()
            messages.success(request, "Client created successfully.")
            return redirect('clients:client_detail', pk=client.pk)
        return render(request, self.template_name, {'form': form, 'action': 'Create'})


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

@method_decorator([login_required, _admin_or_staff_required], name='dispatch')
class ClientUpdateView(View):
    template_name = 'clients/client_form.html'

    def get(self, request, pk):
        client = get_object_or_404(Client.active_objects, pk=pk)
        form = ClientForm(instance=client)
        return render(request, self.template_name, {'form': form, 'client': client, 'action': 'Update'})

    def post(self, request, pk):
        client = get_object_or_404(Client.active_objects, pk=pk)
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            client = form.save(commit=False)
            client.updated_by = request.user
            client.save()
            messages.success(request, "Client updated successfully.")
            return redirect('clients:client_detail', pk=client.pk)
        return render(request, self.template_name, {'form': form, 'client': client, 'action': 'Update'})


# ---------------------------------------------------------------------------
# Delete (soft)
# ---------------------------------------------------------------------------

@method_decorator([login_required, _admin_or_staff_required], name='dispatch')
class ClientDeleteView(View):
    template_name = 'clients/client_confirm_delete.html'

    def get(self, request, pk):
        client = get_object_or_404(Client.active_objects, pk=pk)
        return render(request, self.template_name, {'client': client})

    def post(self, request, pk):
        try:
            ClientService.delete_client(pk, deleted_by=request.user)
            messages.success(request, "Client deleted successfully.")
        except ClientServiceError as exc:
            messages.error(request, str(exc))
        return redirect('clients:client_list')
