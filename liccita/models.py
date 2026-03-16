from django.db import models
from django.conf import settings
from accounts.models import CustomUser
import uuid
    

class EmpresaPerfil(models.Model):
    utilizador = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='empresas_fjl')
    cnpj = models.CharField(max_length=18)
    razao_social = models.CharField(max_length=255)
    palavras_chave = models.JSONField(default=list, blank=True) 
    data_cadastro = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = '"liccita"."empresa_perfil"'
        unique_together = ('utilizador', 'cnpj')

    def __str__(self):
        return f"{self.cnpj} - {self.razao_social}"


class EmpresaCNAE(models.Model):
    empresa = models.ForeignKey(EmpresaPerfil, on_delete=models.CASCADE, related_name='cnaes')
    codigo = models.CharField(max_length=20)
    descricao = models.CharField(max_length=255)
    data_adicao = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"liccita"."empresa_cnae"'
        # Garante que a MESMA empresa não cadastre o MESMO CNAE duas vezes
        unique_together = ('empresa', 'codigo') 

    def __str__(self):
        return f"{self.codigo} - {self.empresa.cnpj}"
    
    
class Modalidade(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    codigo = models.IntegerField(unique=True, help_text="Código numérico usado pela API da fonte.")

    class Meta:
        db_table = '"liccita"."modalidade"'
        ordering = ['nome']
        verbose_name = "Modalidade de Licitação"
        verbose_name_plural = "Modalidades de Licitação"

    def __str__(self):
        return f"{self.nome} (Cód: {self.codigo})"
    

class ModalidadeAlias(models.Model):
    alias = models.CharField(max_length=255, unique=True, db_index=True)
    modalidade_padrao = models.ForeignKey(Modalidade, on_delete=models.SET_NULL, null=True, blank=True, related_name="aliases")

    class Meta:
        db_table = '"liccita"."modalidade_alias"'
        verbose_name = "Sinônimo de Modalidade"
        verbose_name_plural = "Sinônimos de Modalidade"

    def __str__(self):
        padrao = self.modalidade_padrao.nome if self.modalidade_padrao else "PENDENTE"
        return f'"{self.alias}" -> "{padrao}"'
    

class FonteLicitacao(models.Model):
    TIPO_COLETA_CHOICES = [
        ("api", "API"),
        ("rss", "RSS"),
        ("html", "HTML"),
        ("js", "JavaScript"),
    ]
    FORMATO_CHOICES = [
        ("json", "JSON"),
        ("xml", "XML"),
        ("html", "HTML"),
    ]

    nome = models.CharField(max_length=100, unique=True)
    url = models.URLField(max_length=1000)
    tipo = models.CharField(max_length=20, choices=TIPO_COLETA_CHOICES)
    formato = models.CharField(max_length=10, choices=FORMATO_CHOICES)
    rate_limit = models.IntegerField(default=0)
    auth = models.CharField(max_length=100, blank=True, null=True)
    termos_uso = models.TextField(blank=True, null=True)
    campos_disponiveis = models.JSONField(blank=True, null=True)
    frequencia_atualizacao = models.CharField(max_length=50, blank=True, null=True)
    contrato_comercial = models.BooleanField(default=False)
    ativo = models.BooleanField(default=True)
    modalidades_a_coletar = models.ManyToManyField(Modalidade, blank=True)

    class Meta:
        db_table = '"liccita"."fonte_licitacao"'
        verbose_name = "Fonte de Licitação"
        verbose_name_plural = "Fontes de Licitação"

    def __str__(self):
        return self.nome


class Licitacao(models.Model):
    # Campos base nativos para substituir UUIDModel e TimeStampedModel
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Rastreamento de Fonte (SourceTrackedModel)
    source = models.CharField(max_length=100, db_index=True)
    source_id = models.CharField(max_length=255, blank=True, null=True)
    fingerprint = models.CharField(max_length=64, unique=True, db_index=True)

    # Dados da Licitação
    titulo = models.TextField()
    orgao = models.CharField(max_length=255, blank=True, null=True)
    modalidade = models.ForeignKey(Modalidade, on_delete=models.SET_NULL, null=True, blank=True, related_name="licitacoes")
    numero_processo = models.CharField(max_length=100, blank=True, null=True)
    data_publicacao = models.DateTimeField(blank=True, null=True, db_index=True)
    data_abertura = models.DateTimeField(blank=True, null=True)
    valor_estimado = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    descricao = models.TextField(blank=True, null=True)
    edital_url = models.URLField(max_length=1000, blank=True, null=True)
    
    # Removi a FK de 'status' para evitar dependência de app externo, usando CharField simples por enquanto
    status = models.CharField(max_length=50, blank=True, null=True) 
    
    local_cidade = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    local_uf = models.CharField(max_length=2, blank=True, null=True, db_index=True)
    modo_disputa = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    srp = models.BooleanField(null=True, blank=True)
    favoritos = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='editais_salvos', blank=True)

    class Meta:
        db_table = '"liccita"."licitacao"'
        verbose_name_plural = "Licitações"
        indexes = [
            models.Index(fields=["source"]),
            models.Index(fields=["fingerprint"]),
            models.Index(fields=["data_publicacao"]),
        ]

    def __str__(self):
        return f"{self.titulo[:80]}..."

    def save(self, *args, **kwargs):
        import json, hashlib
        if not self.fingerprint:
            raw_data = json.dumps({
                "source": self.source,
                "source_id": self.source_id,
                "titulo": self.titulo,
                "orgao": self.orgao,
                "data_publicacao": str(self.data_publicacao),
            }, sort_keys=True)
            self.fingerprint = hashlib.sha256(raw_data.encode("utf-8")).hexdigest()
        super().save(*args, **kwargs)
        
        
class RaioXPersonalizado(models.Model):
    licitacao = models.ForeignKey(Licitacao, on_delete=models.CASCADE, related_name='raiox_gerados')
    utilizador = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    relatorio_markdown = models.TextField('Relatório da IA')
    data_geracao = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"liccita"."raiox_personalizado"'
        unique_together = ('licitacao', 'utilizador') 

    def __str__(self):
        return f"Raio-X de {self.utilizador.email} para {self.licitacao.orgao}"
    

class AlertaLicitacao(models.Model):
    FREQUENCIA_CHOICES = [
        ('diaria', 'Diária'),
        ('semanal', 'Semanal')
    ]
    CANAL_CHOICES = [
        ('email', 'E-mail'),
        ('whatsapp', 'WhatsApp')
    ]

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='alertas')
    nome = models.CharField(max_length=100, help_text="Ex: Licitações de Software")
    ufs = models.CharField(max_length=100, blank=True, null=True, help_text="Ex: SP, MG, DF (vazio = Brasil todo)")
    valor_minimo = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    frequencia = models.CharField(max_length=20, choices=FREQUENCIA_CHOICES, default='diaria')
    canal = models.CharField(max_length=20, choices=CANAL_CHOICES, default='email')
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    apenas_alto_match = models.BooleanField(default=False, help_text="Se True, a IA fará uma curadoria e enviará apenas editais com +80% de chance de vitória.")
    
    class Meta:
        db_table = '"liccita"."alerta_licitacao"'

    def __str__(self):
        return f"{self.nome} - {self.usuario.email}"
    

class EditalEnviado(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    licitacao = models.ForeignKey(Licitacao, on_delete=models.CASCADE)
    data_envio = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = '"liccita"."edital_enviado"'
        # A trava de ouro: o banco de dados proíbe salvar o mesmo edital pro mesmo usuário
        unique_together = ('usuario', 'licitacao')