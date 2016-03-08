# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django import forms
from django.contrib import admin
from django.contrib.admin import widgets
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.translation import ugettext_lazy as _

from .models import Folder, File, Image, Clipboard, tools, FolderRoot
from . import settings as filer_settings

try:
    from urllib import urlencode
except:  # For Python 3
    from urllib.parse import urlencode

ALLOWED_PICK_TYPES = ('folder', 'file')


class NewFolderForm(forms.ModelForm):
    class Meta(object):
        model = Folder
        fields = ('name',)
        widgets = {
            'name': widgets.AdminTextInputWidget,
        }


def popup_status(request):
    return ('_popup' in request.GET or 'pop' in request.GET or
            '_popup' in request.POST or 'pop' in request.POST)


def popup_pick_type(request):
    # very important to limit the pick_types because the result is marked safe.
    # (injection attacks)
    pick_type = request.GET.get('_pick', request.POST.get('_pick', None))
    if pick_type in ALLOWED_PICK_TYPES:
        return pick_type
    return None


def popup_param(request, separator="?"):
    if popup_status(request):
        return "%s_popup=1" % separator
    else:
        return ""


def admin_url_params(request):
    """
    given a request, looks at GET and POST values to determine which params
    should be added. Is used to keep the context of popup and picker mode.
    """
    # FIXME: put this code in a better location
    params = {}
    if popup_status(request):
        params[admin.options.IS_POPUP_VAR] = '1'
    pick_type = popup_pick_type(request)
    if pick_type:
        params['_pick'] = pick_type
    return params


def admin_url_params_encoded(request, full=True):
    params = urlencode(admin_url_params(request))
    if not params:
        return ''
    if full:
        return '?{}'.format(params)
    return params


class AdminUrlParams(dict):
    def __init__(self, request):
        super(AdminUrlParams, self).__init__()
        self.request = request
        self.update(admin_url_params(request))
        for key, value in self.items():
            if key.startswith('_'):
                self[key[1:]] = value
            if key == '_pick':
                for pick_type in ALLOWED_PICK_TYPES:
                    self['pick_{}'.format(value)] = value == pick_type


def _userperms(item, request):
    r = []
    ps = ['read', 'edit', 'add_children']
    for p in ps:
        attr = "has_%s_permission" % p
        if hasattr(item, attr):
            x = getattr(item, attr)(request)
            if x:
                r.append(p)
    return r


def canonical(request, uploaded_at, file_id):
    """
    Redirect to the current url of a public file
    """
    filer_file = get_object_or_404(File, pk=file_id, is_public=True)
    if (uploaded_at != filer_file.uploaded_at.strftime('%s') or
            not filer_file.file):
        raise Http404('No %s matches the given query.' % File._meta.object_name)
    return redirect(filer_file.url)


@login_required
def make_folder(request, folder_id=None):
    if not folder_id:
        folder_id = request.GET.get('parent_id', None)
    if not folder_id:
        folder_id = request.POST.get('parent_id', None)
    if folder_id:
        folder = Folder.objects.get(id=folder_id)
    else:
        folder = None

    if request.user.is_superuser:
        pass
    elif folder is None:
        # regular users may not add root folders unless configured otherwise
        if not filer_settings.FILER_ALLOW_REGULAR_USERS_TO_ADD_ROOT_FOLDERS:
            raise PermissionDenied
    elif not folder.has_add_children_permission(request):
        # the user does not have the permission to add subfolders
        raise PermissionDenied

    if request.method == 'POST':
        new_folder_form = NewFolderForm(request.POST)
        if new_folder_form.is_valid():
            new_folder = new_folder_form.save(commit=False)
            if (folder or FolderRoot()).contains_folder(new_folder.name):
                new_folder_form._errors['name'] = new_folder_form.error_class(
                    [_('Folder with this name already exists.')])
            else:
                new_folder.parent = folder
                new_folder.owner = request.user
                new_folder.save()
                return render(request, 'admin/filer/dismiss_popup.html')
    else:
        new_folder_form = NewFolderForm()
    return render(request, 'admin/filer/folder/new_folder_form.html', {
        'opts': Folder._meta,
        'new_folder_form': new_folder_form,
        'is_popup': popup_status(request),
        'filer_admin_context': AdminUrlParams(request),
    })


class UploadFileForm(forms.ModelForm):
    class Meta(object):
        model = Image
        exclude = ()


@login_required
def upload(request):
    # FIXME: find out if this is still used (template is missing)
    return render(request, 'filer/upload.html', {
        'title': 'Upload files',
        'is_popup': popup_status(request),
        'filer_admin_context': AdminUrlParams(request),
    })


@login_required
def paste_clipboard_to_folder(request):
    if request.method == 'POST':
        folder = Folder.objects.get(id=request.POST.get('folder_id'))
        clipboard = Clipboard.objects.get(id=request.POST.get('clipboard_id'))
        if folder.has_add_children_permission(request):
            tools.move_files_from_clipboard_to_folder(clipboard, folder)
            tools.discard_clipboard(clipboard)
        else:
            raise PermissionDenied
    redirect = request.GET.get('redirect_to', '')
    if not redirect:
        redirect = request.POST.get('redirect_to', '')
    return HttpResponseRedirect('%s?order_by=-modified_at%s%s' % (
                                redirect,
                                popup_param(request, separator='&'),
                                selectfolder_param(request)))


@login_required
def discard_clipboard(request):
    if request.method == 'POST':
        clipboard = Clipboard.objects.get(id=request.POST.get('clipboard_id'))
        tools.discard_clipboard(clipboard)
    return HttpResponseRedirect('%s%s%s' % (
                                request.POST.get('redirect_to', ''),
                                popup_param(request),
                                selectfolder_param(request)))


@login_required
def delete_clipboard(request):
    if request.method == 'POST':
        clipboard = Clipboard.objects.get(id=request.POST.get('clipboard_id'))
        tools.delete_clipboard(clipboard)
    return HttpResponseRedirect('%s%s%s' % (
                                request.POST.get('redirect_to', ''),
                                popup_param(request),
                                selectfolder_param(request)))


@login_required
def clone_files_from_clipboard_to_folder(request):
    if request.method == 'POST':
        clipboard = Clipboard.objects.get(id=request.POST.get('clipboard_id'))
        folder = Folder.objects.get(id=request.POST.get('folder_id'))
        tools.clone_files_from_clipboard_to_folder(clipboard, folder)
    return HttpResponseRedirect('%s%s%s' % (
                                request.POST.get('redirect_to', ''),
                                popup_param(request),
                                selectfolder_param(request)))
