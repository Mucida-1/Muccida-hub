from django.contrib import admin
from .models import FonteLicitacao, Modalidade, ModalidadeAlias

@admin.register(Modalidade)
class ModalidadeAdmin(admin.ModelAdmin):
    list_display = ('nome', 'codigo')
    search_fields = ('nome', 'codigo')

@admin.register(FonteLicitacao)
class FonteLicitacaoAdmin(admin.ModelAdmin):
    list_display = ('nome', 'tipo', 'formato', 'ativo')
    list_filter = ('tipo', 'formato', 'ativo')

    # Esta linha cria uma interface de seleção muito melhor para ManyToMany
    filter_horizontal = ('modalidades_a_coletar',)

@admin.register(ModalidadeAlias)
class ModalidadeAliasAdmin(admin.ModelAdmin):
    list_display = ('alias', 'modalidade_padrao')
    search_fields = ('alias',)
    # Facilita a seleção da modalidade padrão
    autocomplete_fields = ('modalidade_padrao',)