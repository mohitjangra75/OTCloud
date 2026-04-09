import random
import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.utils import timezone

from accounts.models import OTP

User = get_user_model()
logger = logging.getLogger(__name__)

OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 5


def _clean_mobile(mobile_number: str) -> str:
    """Strip dashes, spaces, and non-digit chars (except leading +)."""
    if mobile_number.startswith('+'):
        return '+' + ''.join(c for c in mobile_number[1:] if c.isdigit())
    return ''.join(c for c in mobile_number if c.isdigit())


class OTPService:
    """Handles OTP generation, sending, and verification."""

    @staticmethod
    def generate_otp(mobile_number: str, purpose: str) -> str:
        """Generate a 6-digit OTP. Reuses existing unexpired OTP if available,
        otherwise invalidates old ones and creates a new one."""
        mobile_number = _clean_mobile(mobile_number)
        cutoff = timezone.now() - timedelta(minutes=OTP_EXPIRY_MINUTES)

        # Check for existing valid OTP - reuse it instead of creating new
        existing = OTP.objects.filter(
            mobile_number=mobile_number,
            purpose=purpose,
            is_used=False,
            created_at__gte=cutoff,
        ).order_by('-created_at').first()

        if existing:
            # Reuse existing valid OTP
            code = existing.otp
        else:
            # Invalidate all old unused OTPs for this mobile+purpose
            OTP.objects.filter(
                mobile_number=mobile_number,
                purpose=purpose,
                is_used=False,
            ).update(is_used=True)

            code = f'{random.randint(0, 999999):06d}'

            OTP.objects.create(
                mobile_number=mobile_number,
                otp=code,
                purpose=purpose,
            )

        # In production, integrate with an SMS gateway here.
        print(f'\n{"=" * 40}')
        print(f'  OTP for {mobile_number}: {code}')
        print(f'  Purpose: {purpose}')
        print(f'{"=" * 40}\n')
        logger.info('OTP generated for %s (purpose=%s)', mobile_number, purpose)

        return code

    @staticmethod
    def verify_otp(mobile_number: str, code: str, purpose: str) -> bool:
        """Verify an OTP. Returns True if valid and not expired."""
        mobile_number = _clean_mobile(mobile_number)
        cutoff = timezone.now() - timedelta(minutes=OTP_EXPIRY_MINUTES)

        otp_record = OTP.objects.filter(
            mobile_number=mobile_number,
            otp=code,
            purpose=purpose,
            is_used=False,
            created_at__gte=cutoff,
        ).order_by('-created_at').first()

        if otp_record is None:
            return False

        # Mark this and all older OTPs as used
        OTP.objects.filter(
            mobile_number=mobile_number,
            purpose=purpose,
            is_used=False,
        ).update(is_used=True)

        return True

    @staticmethod
    def rate_limit_check(mobile_number: str, purpose: str) -> bool:
        """Return True if the mobile number has NOT exceeded the rate limit."""
        mobile_number = _clean_mobile(mobile_number)
        cutoff = timezone.now() - timedelta(hours=1)
        count = OTP.objects.filter(
            mobile_number=mobile_number,
            purpose=purpose,
            created_at__gte=cutoff,
        ).count()
        return count < OTP_MAX_ATTEMPTS


class AuthService:
    """Higher-level authentication operations."""

    @staticmethod
    def create_user(mobile_number: str, password: str, role: str = None, **profile_data) -> User:
        """Create a new user after OTP verification. Prevents duplicates."""
        mobile_number = _clean_mobile(mobile_number)

        # Check if user already exists (e.g. double-submit)
        existing = User.objects.filter(mobile_number=mobile_number).first()
        if existing:
            return existing

        if role not in (User.Role.STAFF, User.Role.CLIENT):
            role = User.Role.CLIENT

        try:
            user = User.objects.create_user(
                mobile_number=mobile_number,
                password=password,
                role=role,
                is_verified=True,
                **profile_data,
            )
        except IntegrityError:
            # Race condition - user was created between check and create
            user = User.objects.get(mobile_number=mobile_number)

        return user

    @staticmethod
    def reset_password(mobile_number: str, new_password: str) -> bool:
        """Reset a user's password. Returns True on success."""
        mobile_number = _clean_mobile(mobile_number)
        try:
            user = User.objects.get(mobile_number=mobile_number)
        except User.DoesNotExist:
            return False

        user.set_password(new_password)
        user.save(update_fields=['password'])
        return True
