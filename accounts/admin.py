from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Produto, Plano, Assinatura, CupomDesconto

# Configura o visual do CustomUser no painel
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['email', 'cpf_cnpj', 'telefone', 'is_staff']
    search_fields = ['email', 'cpf_cnpj']
    ordering = ['email']
    # Remove as referências ao username antigo
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Informações Pessoais', {'fields': ('cpf_cnpj', 'telefone')}),
        ('Permissões', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Ganchos Financeiros', {'fields': ('gateway_customer_id',)}),
    )

# Registra as tabelas do SaaS
admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Produto)
admin.site.register(Plano)
admin.site.register(Assinatura)
admin.site.register(CupomDesconto)