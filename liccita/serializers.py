from rest_framework import serializers
from django.utils import timezone
from .models import EmpresaCNAE, EmpresaPerfil, Licitacao

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
    

class EditalSerializer(serializers.ModelSerializer):
    uf = serializers.CharField(source='local_uf', default='BR')
    modalidade = serializers.CharField(source='modalidade.nome', default='Não definida')
    objeto = serializers.CharField(source='descricao', default='Sem descrição')
    valorEstimado = serializers.SerializerMethodField()
    dataAbertura = serializers.SerializerMethodField()
    diasRestantes = serializers.SerializerMethodField()
    matchTags = serializers.SerializerMethodField()
    matchCnae = serializers.SerializerMethodField()
    salvo = serializers.BooleanField(default=False) # No futuro ligamos à tabela de favoritos

    class Meta:
        model = Licitacao
        fields = [
            'id', 'orgao', 'uf', 'modalidade', 'objeto', 
            'valorEstimado', 'dataAbertura', 'diasRestantes', 
            'matchTags', 'matchCnae', 'salvo', 'edital_url'
        ]

    def get_valorEstimado(self, obj):
        if obj.valor_estimado:
            # Formata para o padrão brasileiro: R$ 1.500.000,00
            return f"R$ {obj.valor_estimado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return "A consultar"

    def get_dataAbertura(self, obj):
        if obj.data_abertura:
            return obj.data_abertura.strftime('%d/%m/%Y')
        return "Data não informada"

    def get_diasRestantes(self, obj):
        if obj.data_abertura:
            hoje = timezone.now().date()
            abertura = obj.data_abertura.date()
            delta = (abertura - hoje).days
            return delta if delta > 0 else 0
        return 0

    def get_matchTags(self, obj):
        # A View vai injetar as tags que deram match neste objeto!
        return getattr(obj, 'matched_tags', [])

    def get_matchCnae(self, obj):
        return getattr(obj, 'matched_cnae', 'Análise de Texto')