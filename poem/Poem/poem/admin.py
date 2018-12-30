from django.http import HttpResponseRedirect
from django.urls import reverse
from django.contrib import admin
from django.contrib.auth.models import Group
from django.contrib.admin.sites import AdminSite
from django.views.decorators.cache import never_cache
from django.template.response import TemplateResponse

from Poem.poem.admin_interface.grmetrics import GroupOfMetricsAdmin
from Poem.poem.admin_interface.grprobes import GroupOfProbesAdmin
from Poem.poem.admin_interface.grprofiles import GroupOfProfilesAdmin
from Poem.poem.admin_interface.sitemetrics import *
from Poem.poem.admin_interface.siteprobes import *
from Poem.poem.admin_interface.siteprofile import *
from Poem.poem.admin_interface.userprofile import *
from Poem.poem.models import GroupOfMetrics, GroupOfProfiles
from Poem.poem.models import MetricInstance, Metric, Probe, Profile, UserProfile, VO, ServiceFlavour, GroupOfProfiles, CustUser
from Poem.settings import SAMLLOGINSTRING

from Poem.api.admin import MyAPIKeyAdmin
from rest_framework_api_key.models import APIKey

import re


class PublicViews(object):
    def load_settings(self):
        self.public_models = (Probe, Metric, Profile)
        self._public_name_models = [s.__name__.lower() for s in self.public_models]
        self._map = dict()
        _ = [self._map.update({x.__name__.lower(): x}) for x in self.public_models]
        self._regex = '(' + '|'.join(self._public_name_models) + ')'

    def get_public_urls(self):
        from django.urls import path, re_path

        public_urls = list()
        public_urls.append(re_path('^poem/public_(?P<model>%s)/$' %
                                   self._regex, self.public_views))
        public_urls.append(re_path('^poem/public_(?P<model>%s)/(?P<object_id>[0-9]+)/change/'
                                   % self._regex, self.public_views))

        return public_urls

    def public_views(self, request, **kwargs):
        objid = kwargs.get('object_id', None)
        model = self._map[kwargs['model']]
        context = dict(self.each_context(request))
        if objid:
            return self._registry[model].change_view(request, objid, extra_context=context)
        else:
            return self._registry[model].changelist_view(request, extra_context=context)

    def login(self, request, extra_context):
        """
        If we are coming from all forms of public changelist_view, like
        /poem/public_probe/, /poem/public_probe/?, /poem/public_probe/?all=,
        /poem/public_probe/?group=GROUP, /poem/public_probe/?all=&group=GROUP,
        /poem/public_probe/poem/?p=5 or /poem/public_probe/?q=term
        and ask for individual change_view for Probe, then proceed without
        authentication.

        Also, if we are coming from invidiual change_view of the probe like
        /poem/public_probe/87/change want to go to changelist_view, then
        proceed without authentication.
        """

        prev = request.META.get('HTTP_REFERER', None)
        # prev = None
        if prev:
            context = dict(self.each_context(request))
            next_url = request.GET.get('next')

            # changelist_view -> change_view
            r = re.search('public_(\w+)/(\?)?(\?p=[0-9]+)?(\?q=\w+)?(\?all\=)?([\&\?]group\=[\w\-]+)?$', prev)
            if r:
                objid = re.search('([0-9]+)', next_url)
                if objid:
                    objid = objid.group(1)
                    url = reverse('admin:poem_%s_change' % r.group(1), args=(objid,))
                    url = url.replace(r.group(1) + '/',
                                      'public_%s/' % r.group(1))

                    return HttpResponseRedirect(url)

            # change_view -> changelist_view
            r = re.search('public_(\w+)/([0-9]+)/change/$', prev)
            if r:
                url = reverse('admin:poem_%s_changelist' % r.group(1))
                url = url.replace(r.group(1) + '/',
                                  'public_%s/' % r.group(1))

                return HttpResponseRedirect(url)

        return super().login(request, extra_context)


class MyAdminSite(PublicViews, AdminSite):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        super().load_settings()

    @never_cache
    def index(self, request, extra_context=None):
        if request.user.is_authenticated:
            if request.user.is_superuser:
                return HttpResponseRedirect(request.path + 'poem')
            else:
                return HttpResponseRedirect(request.path + 'poem/profile')

    @never_cache
    def login(self, request, extra_context=None):
        """
        Extend login view with SAML login string and call PublicViews.login()
        """
        extra_context = extra_context if extra_context else dict()
        extra_context.update(samlloginstring=SAMLLOGINSTRING)

        return super().login(request, extra_context)

    def app_index(self, request, app_label, extra_context=None):
        if request.user.is_authenticated:
            if request.user.is_superuser:
                poem_app_name, apikey_app = 'poem', 'rest_framework_api_key'

                if request.path.endswith('admin/%s/' % apikey_app):
                    return HttpResponseRedirect('/%s/admin/%s/' % (poem_app_name, poem_app_name))

                # Reorganize administration page by grouping type of data that
                # want to be administered:
                #   Poem = Metrics, Probes, Profiles
                #   Authnz = GroupOfMetrics, GroupOfProbes, GroupOfProfiles, Users
                #   API Permissions = API keys
                app_list = self.get_app_list(request)
                authnz = dict(
                    name='Authentication and Authorization',
                    app_label='authnz',
                    app_url='/poem/admin/poem',
                    has_module_perms=True,
                    models=list()
                )
                extract = set(['GroupOfProbes', 'GroupOfMetrics',
                               'GroupOfProfiles', 'CustUser'])

                for a in app_list:
                    if a['app_label'] == poem_app_name:
                        for m in a['models']:
                            if m['object_name'] in extract:
                                authnz['models'].append(m)
                        a['models'] = list(filter(lambda x: x['object_name']
                                                  not in extract, a['models']))
                app_list.append(authnz)

                order = [poem_app_name, 'authnz', apikey_app]
                app_list = sorted(app_list, key=lambda a: order.index(a['app_label']))

                extra_context = dict(
                    self.each_context(request),
                    app_list=app_list,
                )
                extra_context.update(extra_context or {})

                request.current_app = self.name

                return super().app_index(request, app_label, extra_context)
            else:
                return HttpResponseRedirect(request.path + 'profile')

    def get_urls(self):
        """
        Add public url mappings to views so that we can bypass permission
        checks implied in admin_view() decorator
        """
        return super().get_urls() + super().get_public_urls()

    def publicprobe_changelistview(self, request):
        context = dict(self.each_context(request))
        return self._registry[Probe].changelist_view(request, extra_context=context)

    def publicprobe_changeview(self, request, object_id):
        context = dict(self.each_context(request))
        return self._registry[Probe].change_view(request, object_id, extra_context=context)

    @never_cache
    def logout(self, request, extra_context=None):
        super().logout(request, extra_context=extra_context)
        return HttpResponseRedirect(reverse('admin:index'))


myadmin = MyAdminSite()

myadmin.register(Profile, ProfileAdmin)
myadmin.register(Probe, ProbeAdmin)
myadmin.register(Metric, MetricAdmin)
myadmin.register(GroupOfProfiles, GroupOfProfilesAdmin)
myadmin.register(GroupOfMetrics, GroupOfMetricsAdmin)
myadmin.register(GroupOfProbes, GroupOfProbesAdmin)
myadmin.register(CustUser, UserProfileAdmin)
myadmin.register(APIKey, MyAPIKeyAdmin)
