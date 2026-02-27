from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
import uuid

# 1. O Gestor de Utilizadores (Ensina o Django a usar E-mail em vez de Username)
class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('O e-mail é obrigatório para o passaporte MUCCIDA.')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)

# 2. O Passaporte (Utilizador Global)
class CustomUser(AbstractUser):
    username = None
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField('Endereço de E-mail', unique=True)
    cpf_cnpj = models.CharField('CPF ou CNPJ', max_length=18, blank=True, null=True)
    telefone = models.CharField('Telemóvel', max_length=20, blank=True, null=True)
    gateway_customer_id = models.CharField('ID no Gateway de Pagamento', max_length=255, blank=True, null=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return self.email

# 3. Os Produtos (O Catálogo do seu Ecossistema)
class Produto(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    descricao = models.TextField(blank=True, null=True)
    ativo = models.BooleanField(default=True)

    def __str__(self):
        return self.nome

# 4. Os Planos (As Categorias de Visto por Produto)
class Plano(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='planos')
    nome = models.CharField(max_length=100)
    preco_mensal = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    limite_creditos_ia = models.IntegerField(default=0, help_text="Quantos Raio-X a IA pode fazer por mês")
    limite_cnaes = models.IntegerField(default=1)

    def __str__(self):
        return f"{self.produto.nome} - {self.nome}"
    
# 5. O Motor de Cupons
class CupomDesconto(models.Model):
    codigo = models.CharField('Código do Cupom', max_length=50, unique=True) # Ex: BLACKFRIDAY50
    desconto_percentual = models.IntegerField('Desconto (%)', default=0, help_text="Ex: 50 para metade do preço")
    ativo = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.codigo} - {self.desconto_percentual}% OFF"

# 6. A Assinatura (A Ligação Final que dá o Acesso)
class Assinatura(models.Model):
    STATUS_CHOICES = [
        ('ativo', 'Ativo'),
        ('inativo', 'Inativo'),
        ('cancelado', 'Cancelado'),
        ('pendente', 'Pagamento Pendente')
    ]

    utilizador = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='assinaturas')
    plano = models.ForeignKey(Plano, on_delete=models.RESTRICT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente')
    creditos_ia_disponiveis = models.IntegerField(default=0)
    data_inicio = models.DateTimeField(auto_now_add=True)
    data_renovacao = models.DateTimeField(blank=True, null=True)
    gateway_subscription_id = models.CharField('ID da Assinatura no Gateway', max_length=255, blank=True, null=True)
    forma_pagamento = models.CharField(
        max_length=50, 
        choices=[('cartao', 'Cartão de Crédito'), ('pix', 'PIX'), ('boleto', 'Boleto')],
        blank=True, 
        null=True
    )
    cupom = models.ForeignKey(CupomDesconto, on_delete=models.SET_NULL, null=True, blank=True, help_text="Cupom utilizado nesta assinatura")
    is_cortesia = models.BooleanField('Conta VIP / Cortesia', default=False, help_text="Se marcado, o sistema não exige pagamento e mantém a conta ativa.")

    def __str__(self):
        return f"{self.utilizador.email} | {self.plano.nome} ({self.status})"
