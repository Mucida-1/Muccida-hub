from django.urls import path, include
from .views import *
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
# Isso gera automaticamente as rotas: GET, POST, PUT, DELETE em /api/liccita/alertas/
router.register(r'alertas', AlertaLicitacaoViewSet, basename='alertas')

urlpatterns = [
    path('cnaes/', EmpresaCNAEListCreateView.as_view(), name='cnae-list-create'),
    path('cnaes/<int:pk>/', EmpresaCNAEDeleteView.as_view(), name='cnae-delete'),
    path('empresas/', EmpresaPerfilListCreateView.as_view(), name='empresa-list'),
    path('empresas/<int:pk>/', EmpresaPerfilDetailView.as_view(), name='empresa-detail'),
    path('gerar-tags/', GerarTagsIAView.as_view(), name='gerar-tags'),
    path('buscar-editais/', BuscarEditaisView.as_view(), name='buscar-editais'),
    path('status-disponiveis/', StatusDisponiveisView.as_view(), name='status-disponiveis'),
    path('ufs-disponiveis/', UFsDisponiveisView.as_view(), name='ufs-disponiveis'),
    path('salvar-edital/<uuid:pk>/', AlternarEditalSalvoView.as_view(), name='salvar-edital'),
    path('meus-salvos/', EditaisSalvosView.as_view(), name='meus-salvos'),
    path('dashboard-stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('analisar-ia/<uuid:pk>/', AnalisarEditalIAView.as_view(), name='analisar-ia'),
    path('meus-raio-x/', MeusRaioXListView.as_view(), name='meus_raio_x'),
    path('', include(router.urls)),
]
