from django.db import models
from accounts.models import CustomUser
    

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