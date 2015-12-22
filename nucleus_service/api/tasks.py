from __future__ import absolute_import

from celery import shared_task, Task
from subprocess import Popen, PIPE, check_output, STDOUT, CalledProcessError
import json
import sys, traceback

ISOS_DIR = "/mnt/images"

@shared_task(ignore_result=True)
def submit_computesetjob(cset_job):
    """ This task runs on comet-fe1 therefore database updates can ONLY occur
        using update_computesetjob() which will run on comet-nucleus.
        In addition, since django.db modules are not installed on comet-fe1
        we need to use json module to deserialize/serialize JSON.
    """
    from api.tasks import update_computesetjob
    import uuid

    cset_job["name"] = "VC-JOB-%s-%s" % (cset_job["computeset"],
        str(uuid.uuid1()).replace('-',''))
    cset_job["jobid"] = None
    cset_job["error"] = None

    # There are a number of potentilly configurable parameters in the following call
    # to sbatch..
    #
    # workdir=/tmp will leave the job .out file on the EXEC_HOST in /tmp
    # partition=virt will submit jobs to the virt partition
    # signal=B:USR1@60 will send a USR1 signal to the batch script running on the
    # EXEC_HOST. The signal will be caught by the signal_handler and the jobscript
    # should request shutdown of the virtual compute nodes.
    #
    # All other parameters should be considered UNCHANGABLE.

    cmd = ['/usr/bin/timeout',
        '2',
        '/usr/bin/sbatch',
        '--job-name=%s' % (cset_job['name']),
        '--output=%s.out' % (cset_job['name']),
	    '--uid=%s' % (cset_job['user']),
	    '--account=%s' % (cset_job['account']),
        '--workdir=/tmp',
        '--parsable',
        '--partition=virt',
        '--nodes=%s-%s' % (cset_job['node_count'], cset_job['node_count']),
        '--ntasks-per-node=1',
        '--cpus-per-task=24',
        '--signal=B:USR1@60',
        '--time=%s' % (cset_job['walltime_mins']),
        '/etc/slurm/VC-JOB.run',
        '%s' % (cset_job['walltime_mins'])]

    try:
        output = check_output(cmd, stderr=STDOUT)
        cset_job["jobid"] = output.rstrip().strip()
        cset_job["state"] = "submitted"
        update_computesetjob.delay(cset_job)

    except OSError as e:
        cset_job["state"] = "failed"
        msg = "OSError: %s" % (e)
        update_computesetjob.delay(cset_job)

    except CalledProcessError as e:
        cset_job["state"] = "failed"
        if e.returncode == 124:
            msg = "CalledProcessError: Timeout during request: %s" % (e.output.strip().rstrip())
        else:
            msg = "CalledProcessError: %s" % (e.output.strip().rstrip())
        update_computesetjob.delay(cset_job)


@shared_task(ignore_result=True)
def update_computesetjob(cset_job_json):
    """ This task runs on comet-nucleus and can update the database """
    from api.models import ComputeSet
    from api.models import ComputeSetJob
    from api import hostlist

    try:
        cset = ComputeSet.objects.get(id = cset_job_json["computeset"])
    except ComputeSet.DoesNotExist:
        cset = None

    try:
        cset_job, created = ComputeSetJob.objects.get_or_create(
            jobid = cset_job_json["jobid"],
            defaults = {
                'computeset': cset,
                'state': cset_job_json["state"],
                'walltime_mins': 5}
        )

	    # The following will typically only exist or be set on submit...
        if created:
            if ("name" in cset_job_json):
                cset_job.name = cset_job_json["name"]

            if ("user" in cset_job_json):
                cset_job.user = cset_job_json["user"]

            if("account" in cset_job_json):
                cset_job.account = cset_job_json["account"]

            if ("walltime_mins" in cset_job_json):
                cset_job.walltime_mins = cset_job_json["walltime_mins"]

            if ("node_count" in cset_job_json):
                cset_job.node_count = cset_job_json["node_count"]

            cset_job.save()

	    #The following will only exist after jobscript barrier...
        if ("nodelist" in cset_job_json):
            cset_job.nodelist = cset_job_json["nodelist"]
            cset_job.save()

        old_csest_job_state = None
        if ("state" in cset_job_json):
            old_cset_job_state = cset_job.state
            if (cset_job.state != cset_job_json["state"]):
                cset_job.state = cset_job_json["state"]
                cset_job.save()

            # Job passed from SUBMITTED to RUNNING state...
            if (
                old_cset_job_state == ComputeSetJob.CSETJOB_STATE_SUBMITTED and
                cset_job.state == ComputeSetJob.CSETJOB_STATE_RUNNING
                ):
                if cset_job.nodelist is not None:
                    cset = ComputeSet.objects.get(pk=cset_job.computeset_id)
                    nodes = []
                    for compute in cset.computes.all():
                        nodes.append(compute.rocks_name)

                    hosts = hostlist.expand_hostlist("%s" % cset_job.nodelist)
                    # TODO: vlan & switchport configuration
                    poweron_nodeset.delay(nodes, hosts)

            # Job passed from SUBMITTED to COMPLETED state directly...
            if (
                old_cset_job_state == ComputeSetJob.CSETJOB_STATE_SUBMITTED and
                cset_job.state == ComputeSetJob.CSETJOB_STATE_COMPLETED
                ):
                if cset_job.nodelist is not None:
                    hosts = hostlist.expand_hostlist("%s" % cset_job.nodelist)
                    # TODO: anything else todo?

            # Job passed from RUNNING to COMPLETED state...
            if (
                old_cset_job_state == ComputeSetJob.CSETJOB_STATE_RUNNING and
                cset_job.state == ComputeSetJob.CSETJOB_STATE_COMPLETED
                ):
                if cset_job.nodelist is not None:
                    nodes = [compute['name'] for compute in cset.computes]
                    poweroff_nodes.delay(nodes, "shutdown")
                    # TODO: vlan & switchport de-configuration

    except ComputeSetJob.DoesNotExist:
        cset_job = None
        msg = "update_computesetjob: %s" % ("ComputeSetJob (%d) does not exist" % (cset_job_json["computeset"]))

@shared_task(ignore_result=True)
def poweron_nodeset(nodes, hosts, iso_name):
    if(hosts and (len(nodes) != len(hosts))):
        print "hosts length is not equal to nodes"
        return
    outb = ""
    errb = ""

    if(hosts):
        for node, host in zip(nodes, hosts):
            res = Popen(["/opt/rocks/bin/rocks", "set", "host", "vm", "%s"%node, "physnode=%s"%host], stdout=PIPE, stderr=PIPE)
            out, err = res.communicate()
            outb += out
            errb += err

    if(iso_name):
        (ret_code, out, err) = _attach_iso(nodes, iso_name)
        if(ret_code):
            outb += out
            errb += err
            return "Error adding iso to nodes: %s\n%s"%(outb, errb)

    (ret_code, out, err) = _poweron_nodes(nodes)
    if (ret_code):
        outb += out
        errb += err
        return "Error powering on nodes: %s\n%s"%(outb, errb)

@shared_task(ignore_result=True)
def poweroff_nodes(nodes, action):
    (ret_code, out, err) = _poweroff_nodes(nodes, action)
    if (ret_code):
        return "%s\n%s" % (out, err)

# Local function to be called from multiple tasks
def _poweroff_nodes(nodes, action):
    args = ["/opt/rocks/bin/rocks", "stop", "host", "vm"]
    args.extend(nodes)
    args.append("action=%s"%action)
    res = Popen(args, stdout=PIPE, stderr=PIPE)
    out, err = res.communicate()
    return (res.returncode, out, err)

@shared_task(ignore_result=True)
def attach_iso(nodes, iso_name):
    (ret_code, out, err) = _attach_iso(nodes, iso_name)
    if(ret_code):
        return "%s\n%s"%(out, err)

# Local function to be called from multiple tasks
def _attach_iso(nodes, iso_name):
    args = ["/opt/rocks/bin/rocks", "set", "host", "vm", "cdrom"]
    args.extend(nodes)
    if(iso_name):
        args.append("cdrom=%s/%s"%(ISOS_DIR, iso_name))
    else:
        args.append("cdrom=none")
    res = Popen(args, stdout=PIPE, stderr=PIPE)
    out, err = res.communicate()
    return (res.returncode, out, err)

@shared_task(ignore_result=True)
def poweron_nodes(nodes):
    (ret_code, out, err) = _poweron_nodes(nodes)
    if (ret_code):
        return "%s\n%s" % (out, err)

# Local function to be called from multiple tasks
def _poweron_nodes(nodes):
    args = ["/opt/rocks/bin/rocks", "start", "host", "vm"]
    args.extend(nodes)
    res = Popen(args, stdout=PIPE, stderr=PIPE)
    out, err = res.communicate()
    return (res.returncode, out, err)

@shared_task(ignore_result=True)
def update_clusters(clusters_json):
    from api.models import Cluster, Frontend, Compute, ComputeSet, FrontendInterface, ComputeInterface, COMPUTESET_STATE_STARTED, COMPUTESET_STATE_COMPLETED, COMPUTESET_STATE_QUEUED
    for cluster_rocks in clusters_json:
        try:
            cluster_obj = Cluster.objects.get(frontend__rocks_name=cluster_rocks["frontend"])

            if(cluster_obj.vlan != cluster_rocks["vlan"]):
                cluster_obj.vlan = cluster_rocks["vlan"]
                cluster_obj.save()

            frontend = Frontend.objects.get(rocks_name = cluster_rocks["frontend"])
            if(frontend.state != cluster_rocks["state"] or frontend.memory != cluster_rocks["mem"] or frontend.cpus != cluster_rocks["cpus"]):
                frontend.state = cluster_rocks["state"]
                frontend.memory = cluster_rocks["mem"]
                frontend.cpus = cluster_rocks["cpus"]
                frontend.save()
        except Cluster.DoesNotExist:
            frontend = Frontend()
            frontend.name = cluster_rocks["frontend"]
            frontend.rocks_name = cluster_rocks["frontend"]
            frontend.state = cluster_rocks["state"]
            frontend.memory = cluster_rocks["mem"]
            frontend.cpus = cluster_rocks["cpus"]
            frontend.type = cluster_rocks["type"]
            frontend.save()

            cluster_obj = Cluster()
            cluster_obj.name = cluster_rocks["frontend"]
            cluster_obj.vlan = cluster_rocks["vlan"]
            cluster_obj.frontend = frontend
            cluster_obj.save()

        cluster_obj = Cluster.objects.get(frontend__rocks_name=cluster_rocks["frontend"])
        frontend = Frontend.objects.get(rocks_name = cluster_rocks["frontend"])
        for interface in cluster_rocks['interfaces']:
            if(interface["mac"]):
                if_obj, created = FrontendInterface.objects.update_or_create(frontend = frontend, ip = interface["ip"], netmask = interface["netmask"], mac = interface["mac"], iface=interface["iface"], subnet=interface["subnet"])

        for compute_rocks in cluster_rocks["computes"]:
            compute_obj, created = Compute.objects.get_or_create(rocks_name = compute_rocks["name"], cluster = cluster_obj)
            if(created):
                compute_obj.name = compute_rocks["name"]
                compute_obj.state = compute_rocks["state"]
                compute_obj.memory = compute_rocks["mem"]
                compute_obj.cpus = compute_rocks["cpus"]
                compute_obj.type = compute_rocks["type"]
                compute_obj.save()
            elif(compute_obj.state != compute_rocks["state"] or compute_obj.memory != compute_rocks["mem"] or compute_obj.cpus != compute_rocks["cpus"]):
                compute_obj.state = compute_rocks["state"]
                compute_obj.memory = compute_rocks["mem"]
                compute_obj.cpus = compute_rocks["cpus"]
                compute_obj.save()
                try:
                    cs = ComputeSet.objects.get(computes__id__exact=compute_obj.id, state__in=[COMPUTESET_STATE_QUEUED, COMPUTESET_STATE_STARTED])
                    if cs.state == COMPUTESET_STATE_QUEUED and compute_obj.state == "active":
                        cs.state = COMPUTESET_STATE_STARTED
                        cs.save()
                    elif cs.state == COMPUTESET_STATE_STARTED and (not cs.computes.filter(state="active")):
                        cs.state = COMPUTESET_STATE_COMPLETED
                        cs.save()
                except ComputeSet.DoesNotExist:
                    print "Computeset for compute %s not found"%compute_obj.name
                except:
                    print traceback.format_exc()

            for interface in compute_rocks['interfaces']:
                if(interface["mac"]):
                    if_obj, created = ComputeInterface.objects.update_or_create(compute = compute_obj, ip = interface["ip"], netmask = interface["netmask"], mac = interface["mac"], iface=interface["iface"], subnet=interface["subnet"])
