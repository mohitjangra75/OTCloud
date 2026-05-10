"""
Idempotently create / update an admin user from environment variables.

Designed for Render's free tier (no shell access). Wire it into the Render
Start Command so every deploy guarantees an admin exists:

    python manage.py migrate --noinput && \\
    python manage.py ensure_admin && \\
    gunicorn OTCloud.wsgi

Required env vars:
    ADMIN_MOBILE     — mobile number used to log in
    ADMIN_PASSWORD   — password (only applied on first creation)

Optional env vars:
    ADMIN_FIRST_NAME — defaults to "Admin"
    ADMIN_LAST_NAME  — defaults to ""
    ADMIN_RESET_PW   — set to "1" to force-overwrite the password every run

If ADMIN_MOBILE / ADMIN_PASSWORD aren't set, the command logs a warning and
exits 0 so deploys don't fail.
"""
import os

from django.core.management.base import BaseCommand

from accounts.models import User


class Command(BaseCommand):
    help = 'Idempotently provision an admin user from env vars.'

    def handle(self, *args, **options):
        mobile = (os.environ.get('ADMIN_MOBILE') or '').strip()
        password = os.environ.get('ADMIN_PASSWORD') or ''
        first = (os.environ.get('ADMIN_FIRST_NAME') or 'Admin').strip()
        last = (os.environ.get('ADMIN_LAST_NAME') or '').strip()
        force_reset = os.environ.get('ADMIN_RESET_PW') == '1'

        if not mobile or not password:
            self.stdout.write(self.style.WARNING(
                'ensure_admin: skipped — set ADMIN_MOBILE and ADMIN_PASSWORD '
                'env vars to provision an admin user.'
            ))
            return

        user, created = User.objects.get_or_create(
            mobile_number=mobile,
            defaults={
                'first_name': first,
                'last_name': last,
                'role': User.Role.ADMIN,
                'is_active': True,
                'is_staff': True,
                'is_superuser': True,
            },
        )

        # Always keep flags + name in sync with env vars (so changing
        # ADMIN_FIRST_NAME on Render renames the user on the next deploy).
        changed = False
        if user.role != User.Role.ADMIN:
            user.role = User.Role.ADMIN; changed = True
        if not user.is_staff:
            user.is_staff = True; changed = True
        if not user.is_superuser:
            user.is_superuser = True; changed = True
        if not user.is_active:
            user.is_active = True; changed = True
        if first and user.first_name != first:
            user.first_name = first; changed = True
        if last and user.last_name != last:
            user.last_name = last; changed = True

        if created or force_reset:
            user.set_password(password)
            changed = True

        if changed:
            user.save()

        action = 'created' if created else ('reset' if force_reset else 'verified')
        self.stdout.write(self.style.SUCCESS(
            f'ensure_admin: {action} admin {mobile} ({user.get_full_name() or "no name"})'
        ))
