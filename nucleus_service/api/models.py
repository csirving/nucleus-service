from django.db import models
from rest_framework import serializers
import django.contrib.auth.models

import subprocess

# #################################################
#  USER
# #################################################

class User(models.Model):
    username = models.CharField(max_length=24)
    created = models.DateTimeField(auto_now_add=True)
    firstname = models.CharField(max_length=100)
    lastname = models.CharField(max_length=100)
    email = models.CharField(max_length=100)            

    class Meta:
        ordering = ('username',)
        
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username',
                  'firstname',
                  'lastname',
                  'email',
                  'created']

# #################################################
#  PROJECT
# #################################################

class Project(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ('name',)

class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['name']

# #################################################
#  STORAGE
# #################################################

class Storage(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ('name',)

class StorageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Storage
        fields = ['name']

# #################################################
#  FRONTEND
# #################################################

class Frontend(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    #name = models.CharField(max_length=100)

    class Meta:
        pass

class FrontendSerializer(serializers.ModelSerializer):
    class Meta:
        model = Frontend

# #################################################
#  GROUP
# #################################################

class Group(models.Model):
    group_id = models.IntegerField()
    state = models.CharField(max_length=100, default="queued")

    @classmethod
    def create(cls, group_id):
        group = cls(group_id=group_id, state="running")
        return group

    class Meta:
        managed = True

class GroupSerializer(serializers.Serializer):
    group_id = serializers.IntegerField()
    state = serializers.CharField(max_length=100)

# #################################################
#  COMPUTE
# #################################################

class Compute(object):
    def __init__(self, cluster_id, compute_id):
        self.name = compute_id

    def poweron(self):
        out, err = subprocess.Popen(['ssh', 'dimm@comet-fe1', '/opt/rocks/bin/rocks start host vm %s'%self.name], stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
        return [out, err]
        

class ComputeSerializer(serializers.Serializer):
    pass

# #################################################
#  CLUSTER
# #################################################

class Cluster(models.Model):
    fe_name = models.CharField(max_length=100)
    description = models.TextField(default="")
    project = models.ForeignKey(django.contrib.auth.models.Group)

    class Meta:
        managed = True

class ClusterSerializer(serializers.ModelSerializer):
    fe_name = serializers.CharField(max_length=100)
    description = serializers.CharField(default="")

    class Meta:
        model = Cluster
        fields = ('fe_name', 'description')

# #################################################
#  STORAGEPOOL
# #################################################

class Storagepool(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ('name',)
        
class StoragepoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = Storagepool
        fields = ['name']

# #################################################
#  CALL
# #################################################

class Call(models.Model):
        CALL_STATUS = (
            (0, 'In progress'),
            (1, 'Done'),
            (2, 'Error')
        )

        created = models.DateTimeField(auto_now_add=True)
        updated = models.DateTimeField(auto_now=True)
        status = models.IntegerField(choices=CALL_STATUS)
        call_id = models.CharField(max_length=128, primary_key=True)
        data = models.TextField()
        url = models.CharField(max_length=256, null=True)

class CallSerializer(serializers.ModelSerializer):
    class Meta:
        model = Call
        #fields = ['name']

