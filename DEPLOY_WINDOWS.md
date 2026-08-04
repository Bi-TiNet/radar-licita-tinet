# Deploy no Windows Server

Pasta recomendada:

C:\\RadarLicita\\licita_isp_alertas

Instalação no PowerShell como Administrador:

cd C:\\RadarLicita\\licita_isp_alertas
python -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install --upgrade pip
.\\.venv\\Scripts\\pip.exe install -r requirements.txt
copy .env.example .env
notepad .env
.\\.venv\\Scripts\\python.exe run.py

Acesse no servidor: http://localhost:8080
Acesse pela rede: http://IP_DO_SERVIDOR:8080
