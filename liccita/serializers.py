from rest_framework import serializers
from django.utils import timezone
from .models import EmpresaCNAE, EmpresaPerfil, Licitacao, RaioXPersonalizado, AlertaLicitacao

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
    salvo = serializers.SerializerMethodField()
    ja_analisado = serializers.SerializerMethodField()

    class Meta:
        model = Licitacao
        fields = [
            'id', 'orgao', 'uf', 'modalidade', 'objeto', 
            'valorEstimado', 'dataAbertura', 'diasRestantes', 
            'matchTags', 'matchCnae', 'salvo', 'edital_url',
            'ja_analisado'
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
    
    def get_salvo(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # Retorna True se o ID do usuário está na lista de favoritos deste edital
            return obj.favoritos.filter(id=request.user.id).exists()
        return False
    
    def get_ja_analisado(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            # Verifica se existe um RaioXPersonalizado para este edital E para este usuário
            # (Usando o related_name 'raiox_gerados' que criamos no model)
            return obj.raiox_gerados.filter(utilizador=request.user).exists()
        return False


class MeusRaioXSerializer(serializers.ModelSerializer):
    licitacao_id = serializers.UUIDField(source='licitacao.id')
    numero = serializers.CharField(source='licitacao.numero_processo', default='N/A')
    orgao = serializers.CharField(source='licitacao.orgao')
    objeto = serializers.CharField(source='licitacao.titulo')
    modalidade = serializers.CharField(source='licitacao.modalidade.nome', default='Não definida')
    valorEstimado = serializers.SerializerMethodField()
    status = serializers.CharField(source='licitacao.status', default='Aberto')
    
    # NOVOS CAMPOS DE DATA
    dataAbertura = serializers.SerializerMethodField()
    diasRestantes = serializers.SerializerMethodField()

    class Meta:
        model = RaioXPersonalizado
        fields = [
            'id', 'licitacao_id', 'numero', 'orgao', 'objeto', 
            'modalidade', 'valorEstimado', 'status', 
            'relatorio_markdown', 'data_geracao',
            'dataAbertura', 'diasRestantes' # Adicione na lista!
        ]

    def get_valorEstimado(self, obj):
        if obj.licitacao.valor_estimado:
            return f"R$ {obj.licitacao.valor_estimado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return "A consultar"

    # FUNÇÕES PARA PEGAR A DATA DO EDITAL ORIGINAL
    def get_dataAbertura(self, obj):
        if obj.licitacao.data_abertura:
            # Mostra data e hora para ficar bem preciso
            return obj.licitacao.data_abertura.strftime('%d/%m/%Y %H:%M')
        return "Não informada"

    def get_diasRestantes(self, obj):
        if obj.licitacao.data_abertura:
            hoje = timezone.now().date()
            abertura = obj.licitacao.data_abertura.date()
            delta = (abertura - hoje).days
            return delta if delta > 0 else 0
        return 0
    

class AlertaLicitacaoSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertaLicitacao
        fields = '__all__'
        read_only_fields = ['usuario', 'criado_em']

    def validate_canal(self, value):
        if value == 'whatsapp':
            request = self.context.get('request')
            
            if request and request.user:
                usuario = request.user
                
                # Regra 1: Admin do sistema tem passe livre
                if usuario.is_superuser:
                    return value
                    
                # Regra 2: Verifica OBRIGATORIAMENTE se o plano dele é o Profissional
                assinatura = usuario.assinaturas.filter(
                    plano__nome__icontains='profissional'
                ).first()
                
                # Se não encontrou assinatura Pro (ou seja, ele tem o Básico, mesmo sendo VIP) -> Bloqueia.
                if not assinatura:
                    raise serializers.ValidationError(
                        "Ação bloqueada: O envio por WhatsApp requer o Plano Profissional."
                    )

                # Regra 3: O Ferrolho Financeiro (Agora respeitando a Cortesia)
                # Se ele NÃO for VIP, a assinatura obrigatoriamente precisa estar 'ativo'
                if not assinatura.is_cortesia and assinatura.status != 'ativo':
                    raise serializers.ValidationError(
                        "Sua assinatura encontra-se inativa ou com pendências. Regularize para utilizar o WhatsApp."
                    )
        
        # Se passou: ele tem o Plano Pro E (pagou em dia OU é VIP)
        return value