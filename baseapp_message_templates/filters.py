from django import template
from django.contrib.humanize.templatetags.humanize import intcomma

register = template.Library()


def format_money(value, round_amount=False) -> str:
    if value is None:
        return ""
    return "$" + ("{:,.0f}" if round_amount else "{:,.2f}").format(float(value))


def format_phone_number(phone_number: str) -> str:
    return f"{phone_number[0:3]}.{phone_number[3:6]}.{phone_number[6:]}"


@register.filter
def as_percentage(value, round=False) -> str:
    return ("{0:.0f}%" if round else "{0:.1f}%").format(100 * value)


@register.filter
def as_money(value, round_amount=False) -> str:
    return format_money(value or 0, round_amount)


@register.filter
def format_phone(value) -> str | None:
    if not value:
        return None
    return format_phone_number(value)


@register.filter(name="currency")
def currency(dollars) -> str:
    dollars = round(float(dollars), 2)
    return "$%s%s" % (intcomma(int(dollars)), ("%0.2f" % dollars)[-3:])


register.filter("currency", currency)
