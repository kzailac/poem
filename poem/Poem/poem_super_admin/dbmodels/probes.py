from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from reversion.models import Revision, Version
from reversion.signals import post_revision_commit
from tenant_schemas.utils import get_public_schema_name, schema_context

from Poem.tenants.models import Tenant


class Probe(models.Model):
    name = models.CharField(max_length=128, null=False,
                            help_text='Name of the probe.', unique=True)
    version = models.CharField(max_length=28, help_text='Version of the probe.')
    nameversion = models.CharField(max_length=128, null=False,
                                   help_text='Name, version tuple.')
    description = models.CharField(max_length=1024)
    comment = models.CharField(max_length=512)
    repository = models.CharField(max_length=512)
    docurl = models.CharField(max_length=512)
    user = models.CharField(max_length=32, blank=True)
    datetime = models.DateTimeField(blank=True, max_length=32, null=True)

    class Meta:
        verbose_name = 'Probe'
        app_label = 'poem_super_admin'

    def __str__(self):
        return u'%s (%s)' % (self.name, self.version)


@receiver(pre_save, sender=Probe)
def probe_handler(sender, instance, **kwargs):
    instance.nameversion = u'%s (%s)' % (str(instance.name),
                                         str(instance.version))


def create_tenant_revision(revision, sender, signal, versions, **kwargs):
    schemas = list(Tenant.objects.all().values_list('schema_name', flat=True))
    schemas.remove(get_public_schema_name())

    if len(versions) == 1:
        version = versions[0]

    for schema in schemas:
        with schema_context(schema):
            rev = Revision(date_created=revision.date_created,
                           comment=revision.comment,
                           user_id=1)
            rev.save()
            ver = Version(object_id=version.object_id,
                          content_type_id=version.content_type_id,
                          format=version.format,
                          serialized_data=version.serialized_data,
                          object_repr=version.object_repr,
                          db='default',
                          revision=rev)
            ver.save()
post_revision_commit.connect(create_tenant_revision)
