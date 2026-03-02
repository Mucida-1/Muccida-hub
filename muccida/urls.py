from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from accounts.views import CustomTokenObtainPairView, ProdutoPerfilView, CadastroView, LogoutView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Rota de Login usando a nossa View Customizada
    path('api/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/produtos/<int:produto_id>/perfil/', ProdutoPerfilView.as_view(), name='produto_perfil'),
    path('api/cadastro/', CadastroView.as_view(), name='cadastro'),
    path('api/logout/', LogoutView.as_view(), name='logout'),
    path('api/liccita/', include('liccita.urls')),
    path('api/accounts/', include('accounts.urls')),
]