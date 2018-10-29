from django.db import transaction
from django.contrib import admin
from django.contrib import auth
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.forms import ModelForm, Form, CharField, Textarea, ModelChoiceField, \
    ValidationError, ModelMultipleChoiceField, formset_factory
from django.forms.widgets import TextInput, Select
from django.http import HttpResponse
from django.utils.html import format_html
from django.utils.translation import ugettext as _
from Poem.poem import widgets
from Poem.poem.lookups import check_cache
from Poem.poem.admin_interface.formmodel import MyModelMultipleChoiceField, MyModelChoiceField
from Poem.poem.models import Metric, Probe, UserProfile, VO, ServiceFlavour,GroupOfProbes,\
                             CustUser, Tags, Metrics, GroupOfMetrics, MetricAttribute, MetricConfig, MetricParameter,\
                             MetricFlags, MetricDependancy, MetricProbeExecutable, MetricFiles, MetricParent, MetricFileParameter

from ajax_select import make_ajax_field
from reversion_compare.admin import CompareVersionAdmin
from reversion.models import Version
from reversion.admin import VersionAdmin
import reversion
import json
import modelclone
from django.forms.models import BaseInlineFormSet


class SharedInfo:
    def __init__(self, requser=None, grname=None):
        if requser:
            self.__class__.user = requser
        if grname:
            self.__class__.group = grname

    def getgroup(self):
        if getattr(self.__class__, 'group', None):
            return self.__class__.group
        else:
            return None

    def delgroup(self):
        self.__class__.group = None

    def getuser(self):
        if getattr(self.__class__, 'user', None):
            return self.__class__.user
        else:
            return None


class RevisionTemplateTwoForm(Form):
    """
    Mimics the inlines with two fields.
    """
    key = CharField(label='key')
    value = CharField(label='value')


class RevisionTemplateOneForm(Form):
    """
    Mimics the inline with one field.
    """
    value = CharField(label='value')


class MetricAddForm(ModelForm):
    def __init__(self, *args, **kwargs):
        super(MetricAddForm, self).__init__(*args, **kwargs)
        self.fields['group'].widget.can_add_related = False
        self.fields['group'].widget.can_change_related = False
        self.fields['group'].empty_label = None

    class Meta:
        labels = {
            'group': _('Group'),
        }
        help_texts = {
            'group': _('Metric is member of selected group'),
        }

    qs = Tags.objects.all()
    tag = ModelChoiceField(queryset=qs, label='Tag', help_text='Select one of the tags available.')
    tag.empty_label = None
    name = CharField(max_length=255, label='Name', help_text='Metric name',
                     widget=TextInput(attrs={'class': 'metricautocomplete'}))
    probeversion = make_ajax_field(Metric, 'probeversion', 'hintsprobes',
                                   label='Probe', help_text='Probe name and version',
                                   required=False)

    def clean(self):
        try:
            metric = self.cleaned_data['name']
            group = self.cleaned_data.get('group')
        except KeyError as e:
            raise ValidationError('')
        else:
            if group:
                try:
                    Metrics.objects.get(name=metric)
                except Metrics.DoesNotExist:
                    new = Metrics.objects.create(name=metric)
                    GroupOfMetrics.objects.get(name=group).metrics.add(new)
                super(MetricAddForm, self).clean()
            return self.cleaned_data

    def clean_tag(self):
        fetched = self.cleaned_data['tag']
        return Tags.objects.get(id=fetched.id)


class MetricChangeForm(MetricAddForm):
    def __init__(self, *args, **kwargs):
        sh = SharedInfo()
        self.user = sh.getuser()
        self.usergroups = self.user.groupsofmetrics.all()
        super(MetricChangeForm, self).__init__(*args, **kwargs)

    qs = GroupOfMetrics.objects.all()
    group = ModelChoiceField(queryset=qs, widget=Select(),
                                     help_text='Metric is a member of selected group')
    group.empty_label = '----------------'
    group.label = 'Group'

    def clean_group(self):
        groupsel = self.cleaned_data['group']
        gr = SharedInfo(grname=groupsel)
        ugid = [f.id for f in self.usergroups]
        if groupsel.id not in ugid and not self.user.is_superuser:
            raise ValidationError("You are not member of group %s." % (str(groupsel)))
        return groupsel


class MetricAttributeForm(ModelForm):
    key = CharField(label='key')
    value = CharField(label='value')

    def clean(self):
        update_field('attribute', self.cleaned_data, MetricAttribute)

        return super(MetricAttributeForm, self).clean()


class MetricAttributeInline(admin.TabularInline):
    model = MetricAttribute
    verbose_name = 'Attribute'
    verbose_name_plural = 'Attributes'
    form = MetricAttributeForm
    template = 'admin/edit_inline/tabular-attrs.html'
    extra = 1

    def has_add_permission(self, request):
        if request.user.has_perm('poem.groupown_metric') \
                or request.user.is_superuser:
            return True
        else:
            return False

    def has_delete_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True


class MetricParameterForm(ModelForm):
    key = CharField(label='key')
    value = CharField(label='value')

    def clean(self):
        update_field('parameter', self.cleaned_data, MetricParameter)

        return super(MetricParameterForm, self).clean()


class MetricParameterInline(admin.TabularInline):
    model = MetricParameter
    verbose_name = 'Parameter'
    verbose_name_plural = 'Parameter'
    form = MetricParameterForm
    template = 'admin/edit_inline/tabular-attrs.html'
    extra = 1

    def has_add_permission(self, request):
        if request.user.has_perm('poem.groupown_metric') \
                or request.user.is_superuser:
            return True
        else:
            return False

    def has_delete_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True


class MetricFilesForm(ModelForm):
    key = CharField(label='key')
    value = CharField(label='value')

    def clean(self):
        update_field('files', self.cleaned_data, MetricFiles)

        return super(MetricFilesForm, self).clean()


class MetricFilesInline(admin.StackedInline):
    model = MetricFiles
    verbose_name = 'File attributes'
    verbose_name_plural = 'File attributes'
    form = MetricFilesForm
    template = 'admin/edit_inline/tabular-attrs.html'
    extra = 1

    def has_add_permission(self, request):
        if request.user.has_perm('poem.groupown_metric') \
                or request.user.is_superuser:
            return True
        else:
            return False

    def has_delete_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True


class MetricFlagsForm(ModelForm):
    key = CharField(label='key')
    value = CharField(label='value')

    def clean(self):
        update_field('flags', self.cleaned_data, MetricFlags)

        return super(MetricFlagsForm, self).clean()


class MetricFlagsInline(admin.TabularInline):
    model = MetricFlags
    verbose_name = 'Flags'
    verbose_name_plural = 'Flags'
    form = MetricFlagsForm
    template = 'admin/edit_inline/tabular-attrs.html'
    extra = 1

    def has_add_permission(self, request):
        if request.user.has_perm('poem.groupown_metric') \
                or request.user.is_superuser:
            return True
        else:
            return False

    def has_delete_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True


class MetricDependancyForm(ModelForm):
    key = CharField(label='key')
    value = CharField(label='value')

    def clean(self):
        update_field('dependancy', self.cleaned_data, MetricDependancy)

        return super(MetricDependancyForm, self).clean()


class MetricDependancyInline(admin.TabularInline):
    model = MetricDependancy
    verbose_name = 'Dependency'
    verbose_name_plural = 'Dependency'
    form = MetricDependancyForm
    template = 'admin/edit_inline/tabular-attrs.html'
    extra = 1

    def has_add_permission(self, request):
        if request.user.has_perm('poem.groupown_metric') \
                or request.user.is_superuser:
            return True
        else:
            return False

    def has_delete_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True


class MetricConfigForm(ModelForm):
    key = CharField(label='key', widget=TextInput(attrs={'readonly':'readonly'}))
    value = CharField(label='value')

    def clean(self):
        update_field('config', self.cleaned_data, MetricConfig)

        return super(MetricConfigForm, self).clean()


class MetricConfigInlineFormSet(BaseInlineFormSet):
    """
    Formset that manually populates fields for form.
    """
    def __init__(self, *args, **kwargs):
        kwargs['initial'] = [
            {'key': 'interval'}, {'key': 'maxCheckAttempts'}, {'key': 'path'}, {'key': 'retryInterval'}, \
            {'key': 'timeout'},
        ]
        super(MetricConfigInlineFormSet, self).__init__(*args, **kwargs)


class MetricConfigInline(admin.TabularInline):
    model = MetricConfig
    verbose_name = 'Config'
    verbose_name_plural = 'Config'
    form = MetricConfigForm
    template = 'admin/edit_inline/tabular-attrs.html'

    def has_add_permission(self, request):
        if request.user.has_perm('poem.groupown_metric') \
                or request.user.is_superuser:
            return True
        else:
            return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return True


class MetricFileParameterForm(ModelForm):
    key = CharField(label='key')
    value = CharField(label='value')

    def clean(self):
        update_field('fileparameter', self.cleaned_data, MetricFileParameter)

        return super(MetricFileParameterForm, self).clean()


class MetricFileParameterInline(admin.TabularInline):
    model = MetricFileParameter
    verbose_name = 'File parameters'
    verbose_name_plural = 'File parameters'
    form = MetricFileParameterForm
    template = 'admin/edit_inline/tabular-attrs.html'
    extra = 1

    def has_add_permission(self, request):
        if request.user.has_perm('poem.groupown_metric') \
                or request.user.is_superuser:
            return True
        else:
            return False

    def has_delete_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True


class MetricParentForm(ModelForm):
    value = CharField(max_length=255)

    def clean(self):
        update_field('parent', self.cleaned_data, MetricParent)

        return super(MetricParentForm, self).clean()


class MetricParentInline(admin.TabularInline):
    model = MetricParent
    verbose_name = 'Parent metric'
    verbose_name_plural = 'Parent metric'
    form = MetricParentForm
    template = 'admin/edit_inline/tabular-attrs-exec.html'
    max_num = 1
    can_delete = False

    def has_add_permission(self, request):
        if request.user.has_perm('poem.groupown_metric') \
                or request.user.is_superuser:
            return True
        else:
            return False

    def has_delete_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True


class MetricProbeExecutableForm(ModelForm):
    value = CharField(max_length=255)

    def clean(self):
        update_field('probeexecutable', self.cleaned_data, MetricProbeExecutable)

        return super(MetricProbeExecutableForm, self).clean()


class MetricProbeExecutableInline(admin.TabularInline):
    model = MetricProbeExecutable
    verbose_name = 'Probe executable'
    verbose_name_plural = 'Probe executable'
    form = MetricProbeExecutableForm
    template = 'admin/edit_inline/tabular-attrs-exec.html'
    max_num = 1
    can_delete = False

    def has_add_permission(self, request):
        if request.user.has_perm('poem.groupown_metric') \
                or request.user.is_superuser:
            return True
        else:
            return False

    def has_delete_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return True


class MetricAdmin(CompareVersionAdmin, modelclone.ClonableModelAdmin):
    """
    POEM admin core class that customizes its look and feel.
    """
    class Media:
        css = { "all" : ("/poem_media/css/sitemetrics.css",) }


    class GroupMetricsListFilter(admin.SimpleListFilter):
        title = 'metrics group'
        parameter_name = 'group'

        def lookups(self, request, model_admin):
            qs = model_admin.get_queryset(request)
            groups = set(qs.values_list('group__name', flat=True))
            return tuple((x,x) for x in filter(lambda x: x != '', groups))

        def queryset(self, request, queryset):
            if self.value():
                return queryset.filter(group__name=self.value())
            else:
                return queryset

    def probeversion_url(self, obj):
        if obj and obj.probeversion:
            return format_html('<a href="{0}">{1}</a>',
                               reverse('admin:poem_probe_revision',
                                       args=(obj.probekey.object_id,
                                             obj.probekey.pk)),
                               obj.probeversion)
        else:
            return None
    probeversion_url.short_description = 'Probeversion'

    list_display = ('name', 'tag', 'probeversion_url', 'group')
    fieldsets = ((None, {'classes' : ['tagging'], 'fields' : (('name', 'probeversion', 'tag'), 'group')}),)
    list_filter = ('tag', GroupMetricsListFilter,)
    inlines = (MetricProbeExecutableInline, MetricConfigInline,
               MetricAttributeInline, MetricDependancyInline,
               MetricParameterInline, MetricFlagsInline, MetricFilesInline,
               MetricFileParameterInline, MetricParentInline,)
    search_fields = ('name',)
    actions = None
    ordering = ('name',)
    list_per_page = 30

    change_list_template = ''
    object_history_template = ''
    compare_template = ''
    change_form_template = ''

    def get_formsets_with_inlines(self, request, obj=None):
        """
        Control the extra attr value for MetricConfigInline. For change and
        clone view it is set to 0 as we don't want extra empty fields additional
        to ones populated with values from model. For add view we explicitly set
        to 5 and manually populate with MetricConfigInlineFormset that set it to
        needed static keys.
        """
        for inline in self.get_inline_instances(request, obj):
            if isinstance(inline, MetricConfigInline):
                if (request.path.endswith('change/')
                        or request.path.endswith('clone/')):
                    inline.extra = 0
                else:
                    inline.extra = 5
                    inline.formset = MetricConfigInlineFormSet
            yield inline.get_formset(request, obj), inline

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'group' and not request.user.is_superuser:
            lgi = request.user.groupsofmetrics.all().values_list('id', flat=True)
            kwargs["queryset"] = GroupOfMetrics.objects.filter(pk__in=lgi)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def _groupown_turn(self, user, flag):
        perm_prdel = Permission.objects.get(codename='delete_metric')
        try:
            perm_grpown = Permission.objects.get(codename='groupown_metric')
        except Permission.DoesNotExist:
            ct = ContentType.objects.get(app_label='poem', model='metric')
            perm_grpown = Permission.objects.create(codename='groupown_metric',
                                                   content_type=ct,
                                                   name="Group of metric owners")
        if flag == 'add':
            user.user_permissions.add(perm_grpown)
            user.user_permissions.add(perm_prdel)
        elif flag == 'del':
            user.user_permissions.remove(perm_grpown)
            user.user_permissions.remove(perm_prdel)

    def clone_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = extra_context or {}
        extra_context.update({'clone_view': True,
                              'metric_id': object_id,
                              'metric_name': str(Metric.objects.get(pk=object_id)),
                              'original': 'Clone',
                              'title': 'Clone'})
        return super(MetricAdmin, self).clone_view(request, object_id, form_url, extra_context)

    def get_form(self, request, obj=None, **kwargs):
        rquser = SharedInfo(requser=request.user)
        if obj:
            self.form = MetricChangeForm
            ug = request.user.groupsofmetrics.all().values_list('name', flat=True)
            if obj.group.name in ug:
                self._groupown_turn(request.user, 'add')
            else:
                self._groupown_turn(request.user, 'del')
        else:
            self.form = MetricAddForm
            if request.user.groupsofmetrics.count():
                self._groupown_turn(request.user, 'add')
            else:
                self._groupown_turn(request.user, 'del')
        return super(MetricAdmin, self).get_form(request, obj=None, **kwargs)

    @transaction.atomic()
    def delete_model(self, request, obj):
        ct = ContentType.objects.get_for_model(obj)
        lver = reversion.models.Version.objects.filter(object_id=obj.id,
                                                       content_type_id=ct.id)
        ids = map(lambda x: x.revision_id, lver)
        reversion.models.Revision.objects.filter(pk__in=ids).delete()

        return super(MetricAdmin, self).delete_model(request, obj)

    @reversion.create_revision()
    def save_model(self, request, obj, form, change):
        if obj.probeversion:
            obj.probekey = Version.objects.get(object_repr__exact=obj.probeversion)
        if request.path.endswith('/clone/'):
            import re
            cloned_metric = re.search('([0-9]*)/change/clone', request.path).group(1)
            from_metric = Metric.objects.get(pk=cloned_metric)
            reversion.set_user(request.user)
            reversion.set_comment('Derived from %s' % from_metric)
            obj.cloned = cloned_metric
        else:
            obj.cloned = ''
        if request.user.has_perm('poem.groupown_metric') \
                or request.user.is_superuser:
            obj.save()
            return
        else:
            raise PermissionDenied()

    def get_row_css(self, obj, index):
        if not obj.valid:
            return 'row_red red%d' % index
        return ''

    def has_add_permission(self, request):
        if request.user.is_superuser and GroupOfMetrics.objects.count():
            return True
        if request.user.groupsofmetrics.count():
            return True
        else:
            return False

    def has_delete_permission(self, request, obj=None):
        if request.user.has_perm('poem.groupown_metric') \
                or request.user.is_superuser:
            return True
        else:
            return False

    def revision_view(self, request, object_id, version_id, extra_context=None):
        """
        Build custom formsets based on forms.Form and pass them to template
        context. Forms will be populated with the data from corresponding
        Version object bypassing ModelAdmin logic and mimicking ModelAdmin
        change_view with inlines.
        """
        currev = Version.objects.get(pk=version_id).revision.date_created
        data = json.loads(Version.objects.get(pk=version_id).serialized_data)[0]['fields']
        order = [(inline_name.__name__, inline_name.verbose_name) for inline_name in self.inlines]

        version_data_order = list()
        custom_formsets = list()
        verbose_name = {'probeexecutable': 'Probe executable',
                        'attribute': 'Attributes',
                        'config': 'Config',
                        'dependancy': 'Dependency',
                        'parameter': 'Parameter',
                        'flags': 'Flags',
                        'files': 'File attributes',
                        'fileparameter': 'File parameters',
                        'parent': 'Parent metric'}

        for e in order:
            for d in data:
                if e[0].lower().startswith('metric'+d.lower()):
                    value = json.loads(data[d]) if data[d] else ''
                    version_data_order.append({d: value})

        for version in version_data_order:
            element = [(k,v) for (k, v) in version.items()]
            values = element[0]
            settings = values[1]
            if values[0] == 'probeexecutable' or values[0] == 'parent':
                factory = formset_factory(RevisionTemplateOneForm, can_delete=False, extra=1)
                v = settings[0] if settings else ''
                formset = factory(initial=[{'value': v}], prefix=values[0])
                formset.verbose_name = verbose_name[values[0]]
            else:
                initial = list()
                factory = formset_factory(RevisionTemplateTwoForm, can_delete=True, extra=1)
                for s in settings:
                    k, v = s.split(' ', 1)
                    initial.append({'key': k, 'value': v})
                formset = factory(initial=initial, prefix=values[0])
                formset.verbose_name = verbose_name[values[0]]
            custom_formsets.append(formset)

        new_context = {'cursel': currev,
                       'custom_formsets': custom_formsets}
        if extra_context:
            extra_context.update(new_context)
        else:
            extra_context = new_context

        return super(MetricAdmin, self).revision_view(request, object_id, version_id, extra_context)

    def has_change_permission(self, request, obj=None):
        return True


def update_field(field, formdata, model):
    try:
        try:
            newentry = '{0} {1}'.format(formdata['key'], formdata['value'])
        except KeyError:
            newentry = '{0}'.format(formdata['value'])

        deleted = bool(formdata.get('DELETE', False))
        objs = model.objects.filter(metric__exact=formdata['metric'])
        objfield = eval("formdata['metric'].%s" % field)

        fielddata = None
        if deleted and objfield:
            fielddata = json.loads(objfield)
            if formdata['id']:
                index = list(objs).index(formdata['id'])
                if index in fielddata:
                    del fielddata[index]
        else:
            if objfield:
                fielddata = json.loads(objfield)
                if formdata['id']:
                    index = list(objs).index(formdata['id'])
                    fielddata[index] = newentry
                else:
                    fielddata.append(newentry)
            else:
                fielddata = list([newentry])

        codestr = """formdata['metric'].%s = json.dumps(fielddata)""" % field
        exec(codestr)

    except KeyError as e:
        raise ValidationError('')

reversion.register(Metric, exclude=["cloned"])
