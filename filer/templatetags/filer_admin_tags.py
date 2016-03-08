# -*- coding: utf-8 -*-
from django.template import Library
from django.utils.html import mark_safe
from filer.views import admin_url_params, admin_url_params_encoded
from yurl import URL
try:
    import urlparse
    from urllib import urlencode
except:  # For Python 3
    from urllib.parse import urlparse
    from urllib.parse import urlencode


register = Library()


def filer_actions(context):
    """
    Track the number of times the action field has been rendered on the page,
    so we know which value to use.
    """
    context['action_index'] = context.get('action_index', -1) + 1
    return context
filer_actions = register.inclusion_tag(
    "admin/filer/actions.html", takes_context=True)(filer_actions)


@register.simple_tag(takes_context=True)
def filer_admin_context_url_params(context, first_separator='?'):
    return admin_url_params_encoded(
        context['request'], first_separator=first_separator)


@register.simple_tag(takes_context=True)
def filer_admin_context_hidden_formfields(context):
    request = context.get('request')
    fields = [
        '<input type="hidden" name="{}" value="{}">'.format(fieldname, value)
        for fieldname, value in admin_url_params(request).items()
    ]
    return mark_safe('\n'.join(fields))


# @register.filter(is_safe=True, takes_context=True)
# def filer_admin_context_add_url_params(value, full=True):
#     """
#     takes an url as input and adds the additional params for the current admin
#     context. If the input url already defines one of the params, it is not
#     changed.
#     """
#     value = value.strip()
#     url = URL(value)
#     params = urlparse.parse_qs(url.query)
#     context_params = admin_url_params(request)
