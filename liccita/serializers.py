from rest_framework import serializers
from .models import EmpresaCNAE

class EmpresaCNAESerializer(serializers.ModelSerializer):
    class Meta:
        model = EmpresaCNAE
        fields = ['id', 'codigo', 'descricao', 'data_adicao']
        read_only_fields = ['id', 'data_adicao']