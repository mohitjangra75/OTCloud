from django import template

register = template.Library()


@register.filter
def format_duration(td):
    """Format a timedelta as HH:MM:SS. Returns '--' for None values."""
    if td is None:
        return '--'
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(abs(total_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}'
