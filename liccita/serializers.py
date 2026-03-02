from rest_framework import serializers
from .models import EmpresaCNAE, EmpresaPerfil

class EmpresaCNAESerializer(serializers.ModelSerializer):
    class Meta:
        model = EmpresaCNAE
        fields = ['id', 'codigo', 'descricao', 'data_adicao']
        read_only_fields = ['id', 'data_adicao']
        
        
class EmpresaPerfilSerializer(serializers.ModelSerializer):
    # O 'many=True' avisa que vai receber uma lista de CNAEs junto com a Empresa
    utilizador = serializers.HiddenField(default=serializers.CurrentUserDefault())
    cnaes = EmpresaCNAESerializer(many=True)

    class Meta:
        model = EmpresaPerfil
        fields = ['id', 'cnpj', 'razao_social', 'palavras_chave', 'cnaes', 'utilizador']

    def create(self, validated_data):
        cnaes_data = validated_data.pop('cnaes', [])
        # Cria a empresa primeiro
        empresa = EmpresaPerfil.objects.create(**validated_data)
        
        # Depois cria os CNAEs vinculados a ela
        for cnae_data in cnaes_data:
            EmpresaCNAE.objects.create(empresa=empresa, **cnae_data)
        return empresa

    def update(self, instance, validated_data):
        cnaes_data = validated_data.pop('cnaes', [])
        
        # Atualiza os dados da Empresa
        instance.cnpj = validated_data.get('cnpj', instance.cnpj)
        instance.razao_social = validated_data.get('razao_social', instance.razao_social)
        instance.palavras_chave = validated_data.get('palavras_chave', instance.palavras_chave)
        instance.save()

        # Para os CNAEs (Checkboxes), o mais seguro é apagar os antigos e recriar os novos
        instance.cnaes.all().delete()
        for cnae_data in cnaes_data:
            EmpresaCNAE.objects.create(empresa=instance, **cnae_data)
        
        return instance