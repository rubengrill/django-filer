# -*- coding: utf-8 -*-

from django import forms
from django.contrib import admin
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.utils.translation import ugettext as _

from filer import settings
from filer.admin.permissions import PrimitivePermissionAwareModelAdmin
from filer.models import File, Image
from filer.utils.compatibility import LTE_DJANGO_1_5, unquote
from filer.views import (popup_status, AdminUrlParams, admin_url_params_encoded)


class FileAdminChangeFrom(forms.ModelForm):
    class Meta(object):
        model = File
        exclude = ()


class FileAdmin(PrimitivePermissionAwareModelAdmin):
    list_display = ('label',)
    list_per_page = 10
    search_fields = ['name', 'original_filename', 'sha1', 'description']
    raw_id_fields = ('owner',)
    readonly_fields = ('sha1', 'display_canonical')

    # save_as hack, because without save_as it is impossible to hide the
    # save_and_add_another if save_as is False. To show only save_and_continue
    # and save in the submit row we need save_as=True and in
    # render_change_form() override add and change to False.
    save_as = True

    form = FileAdminChangeFrom

    def get_queryset(self, request):
        if LTE_DJANGO_1_5:
            return super(FileAdmin, self).queryset(request)
        return super(FileAdmin, self).get_queryset(request)

    @classmethod
    def build_fieldsets(cls, extra_main_fields=(), extra_advanced_fields=(),
                        extra_fieldsets=()):
        fieldsets = (
            (None, {
                'fields': ('name', 'owner', 'description', ) + extra_main_fields,  # flake8: noqa
            }),
            (_('Advanced'), {
                'fields': ('file', 'sha1', 'display_canonical', ) + extra_advanced_fields,  # flake8: noqa
                'classes': ('collapse',),
            }),
        ) + extra_fieldsets
        if settings.FILER_ENABLE_PERMISSIONS:
            fieldsets = fieldsets + (
                (None, {
                    'fields': ('is_public',)
                }),
            )
        return fieldsets

    def response_change(self, request, obj):
        """
        Overrides the default to be able to forward to the directory listing
        instead of the default change_list_view
        """
        if (
            admin.options.IS_POPUP_VAR in request.POST and
            '_pick' in request.POST and
            '_continue' not in request.POST
        ):
            # popup in pick mode. response_change only gets called if the
            # operation was successful. In pick mode we just want to go
            # back to the folder list view and keep the params.
            if obj.folder:
                url = reverse('admin:filer-directory_listing',
                              kwargs={'folder_id': obj.folder.id})
            else:
                url = reverse(
                    'admin:filer-directory_listing-unfiled_images')
            url = "{}{}".format(
                url,
                admin_url_params_encoded(request),
            )
            return HttpResponseRedirect(url)
        return super(FileAdmin, self).response_change(request, obj)

    def render_change_form(self, request, context, add=False, change=False,
                           form_url='', obj=None):
        extra_context = {'show_delete': True,
                         'is_popup': popup_status(request),
                         'filer_admin_context': AdminUrlParams(request), }
        context.update(extra_context)
        return super(FileAdmin, self).render_change_form(
            request=request, context=context, add=False, change=False,
            form_url=form_url, obj=obj)

    def delete_view(self, request, object_id, extra_context=None):
        """
        Overrides the default to enable redirecting to the directory view after
        deletion of a image.

        we need to fetch the object and find out who the parent is
        before super, because super will delete the object and make it
        impossible to find out the parent folder to redirect to.
        """
        parent_folder = None
        try:
            obj = self.get_queryset(request).get(pk=unquote(object_id))
            parent_folder = obj.folder
        except self.model.DoesNotExist:
            obj = None

        r = super(FileAdmin, self).delete_view(
            request=request, object_id=object_id,
            extra_context=extra_context)

        url = r.get("Location", None)
        # Account for custom Image model
        image_change_list_url_name = 'admin:{0}_{1}_changelist'.format(
            Image._meta.app_label, Image._meta.model_name)
        # Check against filer_file_changelist as file deletion is always made
        # by the base class
        if (url in ["../../../../", "../../"] or
                url == reverse("admin:filer_file_changelist") or
                url == reverse(image_change_list_url_name)):
            if parent_folder:
                url = reverse('admin:filer-directory_listing',
                              kwargs={'folder_id': parent_folder.id})
            else:
                url = reverse('admin:filer-directory_listing-unfiled_images')
            url = "{}{}".format(
                url,
                admin_url_params_encoded(request)
            )
            return HttpResponseRedirect(url)
        return r

    def get_model_perms(self, request):
        """
        It seems this is only used for the list view. NICE :-)
        """
        return {
            'add': False,
            'change': False,
            'delete': False,
        }

    def display_canonical(self, instance):
        canonical = instance.canonical_url
        if canonical:
            return '<a href="%s">%s</a>' % (canonical, canonical)
        else:
            return '-'
    display_canonical.allow_tags = True
    display_canonical.short_description = _('canonical URL')

FileAdmin.fieldsets = FileAdmin.build_fieldsets()
