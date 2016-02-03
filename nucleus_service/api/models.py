import django.contrib.auth.models
from django.db import models

# #################################################
#  FRONTEND
# #################################################


class Frontend(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=100)
    rocks_name = models.CharField(max_length=100, unique=True)
    cpus = models.IntegerField(null=True)
    memory = models.IntegerField(null=True)
    state = models.CharField(max_length=64, null=True)
    type = models.CharField(max_length=16)

    class Meta:
        managed = True


class FrontendInterface(models.Model):
    ip = models.GenericIPAddressField(default='0.0.0.0', null=True)
    netmask = models.GenericIPAddressField(default='0.0.0.0', null=True)
    mac = models.CharField(max_length=17, default='', unique=True)
    iface = models.CharField(max_length=64, default='')
    subnet = models.CharField(max_length=64, null=True)
    frontend = models.ForeignKey(Frontend, related_name='interface')

    class Meta:
        managed = True

# #################################################
#  CLUSTER
# #################################################


class Cluster(models.Model):
    name = models.CharField(max_length=128, unique=True)
    description = models.TextField(default="")
    project = models.ForeignKey(django.contrib.auth.models.Group, null=True)
    frontend = models.ForeignKey(Frontend, related_name='cluster')
    vlan = models.IntegerField(null=True)
    username = models.CharField(max_length=128, null=False) # username under which we run the VMs for the cluster

    class Meta:
        managed = True

class Allocation(models.Model):
    allocation = models.CharField(max_length=128, unique=True)
    cluster = models.ManyToManyField(Cluster, related_name="allocations")

# #################################################
#  COMPUTE
# #################################################


class Compute(models.Model):
    name = models.CharField(max_length=128)
    rocks_name = models.CharField(max_length=128, unique=True)
    cluster = models.ForeignKey(Cluster, related_name='computes')
    host = models.CharField(max_length=128, null=True)
    cpus = models.IntegerField(null=True)
    memory = models.IntegerField(null=True)
    state = models.CharField(max_length=64, null=True)
    type = models.CharField(max_length=16)

    class Meta:
        managed = True


class ComputeInterface(models.Model):
    ip = models.GenericIPAddressField(default='0.0.0.0', null=True)
    netmask = models.GenericIPAddressField(default='0.0.0.0', null=True)
    mac = models.CharField(max_length=17, default='', unique=True)
    compute = models.ForeignKey(Compute, related_name='interface')
    iface = models.CharField(max_length=64, default='')
    subnet = models.CharField(max_length=64, null=True)

    class Meta:
        managed = True

# #################################################
#  NUCLEUSUSER
# #################################################


class NucleusUser(models.Model):
    key_name = models.CharField(max_length=128, primary_key=True)
    user = models.OneToOneField(
        django.contrib.auth.models.User, related_name='api_key')
    secret = models.TextField()

    class Meta:
        managed = True

# #################################################
#  NONCE
# #################################################


class Nonce(models.Model):
    nonce = models.CharField(max_length=128, primary_key=True)
    timestamp = models.IntegerField()

    class Meta:
        managed = True

# #################################################
#  COMPUTESET
# #################################################


class ComputeSet(models.Model):
    CSET_STATE_CREATED = 'created'
    CSET_STATE_SUBMITTED = 'submitted'
    CSET_STATE_FAILED = 'failed'
    CSET_STATE_RUNNING = 'running'
    CSET_STATE_CANCELLED = 'cancelled'
    CSET_STATE_ENDING = 'ending'
    CSET_STATE_COMPLETED = 'completed'
    CSET_STATES = (
        (CSET_STATE_CREATED, 'Created'),
        (CSET_STATE_SUBMITTED, 'Submitted'),
        (CSET_STATE_FAILED, 'Failed'),
        (CSET_STATE_RUNNING, 'Running'),
        (CSET_STATE_CANCELLED, 'Cancelled'),
        (CSET_STATE_ENDING, 'Ending'),
        (CSET_STATE_COMPLETED, 'Completed'),
    )
    computes = models.ManyToManyField(Compute)
    cluster = models.ForeignKey(Cluster)
    jobid = models.PositiveIntegerField(unique=True, null=True)
    name = models.CharField(max_length=64, unique=True, null=True)
    user = models.CharField(max_length=30)
    account = models.CharField(max_length=80)
    walltime_mins = models.PositiveIntegerField()
    nodelist = models.TextField(null=True)
    node_count = models.PositiveIntegerField(null=True)
    state = models.CharField(max_length=128,
                             choices=CSET_STATES,
                             default=CSET_STATE_CREATED)

    class Meta:
        managed = True

# #################################################
#  Network
# #################################################
class Switch(models.Model):
    name = models.CharField(max_length=30)
    ipaddr = models.GenericIPAddressField(protocol='IPv4', blank=True, null=True)


class NetworkPort(models.Model):
    hostname = models.CharField(max_length=20)
    switch = models.ForeignKey(Switch, on_delete=models.CASCADE, blank=True, null=True)
    port = models.CharField(max_length=10)
