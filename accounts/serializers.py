from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from .models import CustomUser, Plano, Assinatura

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        # Pega o token padrão gerado pelo SimpleJWT
        token = super().get_token(user)

        # Injeta os nossos dados customizados
        token['email'] = user.email
        token['is_staff'] = user.is_staff
        
        # Futuramente, quando tivermos o Login do Google, 
        # poderemos injetar a URL da foto de perfil dele aqui também!
        
        return token
    

class CadastroSerializer(serializers.ModelSerializer):
    nome = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True)

    class Meta:
        model = CustomUser
        fields = ('email', 'password', 'nome')

    def create(self, validated_data):
        # 1. Cria o Passaporte MUCCIDA
        user = CustomUser.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data['nome']
        )

        # 2. A Mágica Blindada por ID
        # Aqui nós cravamos as constantes de fundação do sistema
        PRODUTO_FJL_ID = 1
        PLANO_BASICO_ID = 1

        try:
            # Tenta buscar o plano exato pelo ID (muito mais seguro)
            plano_basico = Plano.objects.get(id=PLANO_BASICO_ID, produto_id=PRODUTO_FJL_ID)
            
            Assinatura.objects.create(
                utilizador=user,
                plano=plano_basico,
                status='ativo'
            )
        except Plano.DoesNotExist:
            # Se alguém apagar o plano 1 do banco por engano, 
            # não impedimos o usuário de criar a conta, mas logamos o erro severo.
            print(f"ALERTA CRÍTICO: Plano ID {PLANO_BASICO_ID} ausente! Visto não gerado para {user.email}")

        return user
    
    
class PerfilUsuarioSerializer(serializers.ModelSerializer):
    nome = serializers.CharField(source='first_name')
    
    class Meta:
        model = CustomUser
        fields = ['nome', 'telefone']


class MudarSenhaSerializer(serializers.Serializer):
    atual = serializers.CharField(required=True)
    nova = serializers.CharField(required=True)
    # Não precisamos da 'confirmacao' aqui porque o Front-end já bloqueia se não for igual,
    # e o Django vai ignorar os campos extras enviados pelo Vue.

    def validate_atual(self, value):
        # Pega o usuário que está fazendo a requisição
        user = self.context['request'].user
        
        # O check_password do Django compara o texto limpo com o hash do banco
        if not user.check_password(value):
            raise serializers.ValidationError("A senha atual está incorreta.")
        return value