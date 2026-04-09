from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from accounts.models import OTP, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'mobile_number', 'first_name', 'last_name', 'role',
        'is_verified', 'is_active', 'date_joined',
    )
    list_filter = ('role', 'is_verified', 'is_active')
    search_fields = ('mobile_number', 'first_name', 'last_name', 'email')
    ordering = ('-date_joined',)

    # Fields shown when editing an existing user
    fieldsets = (
        (None, {'fields': ('mobile_number', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'email', 'profile_image')}),
        ('Roles & Permissions', {
            'fields': ('role', 'is_verified', 'is_active', 'is_superuser', 'groups', 'user_permissions'),
        }),
    )

    # Fields shown when creating a new user via admin
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('mobile_number', 'password1', 'password2', 'role'),
        }),
    )

    # Tell Django admin which field is the username
    # (BaseUserAdmin expects this for the add form)
    def get_fieldsets(self, request, obj=None):
        if not obj:
            return self.add_fieldsets
        return super().get_fieldsets(request, obj)


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = ('mobile_number', 'otp', 'purpose', 'is_used', 'created_at')
    list_filter = ('purpose', 'is_used')
    search_fields = ('mobile_number',)
    readonly_fields = ('mobile_number', 'otp', 'purpose', 'created_at')
    ordering = ('-created_at',)
