import sys
import re
import requests
import time
import os
import json
import base64
import math
from datetime import datetime
import streamlit as st
import pandas as pd
from PIL import Image
import pytesseract
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# Tenta importar o leitor de PDF
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

# Configuração da Página
st.set_page_config(page_title="LoGuii - Rotas", layout="wide", page_icon="logo.png")

# Ajuste do Tesseract
if sys.platform.startswith('win'):
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Diretórios e Arquivos Locais
diretorio_atual = os.path.dirname(os.path.abspath(__file__))
caminho_caricatura = os.path.join(diretorio_atual, "caricatura.png")
caminho_logo = os.path.join(diretorio_atual, "logo.png")
arquivo_historico = os.path.join(diretorio_atual, "historico_rotas.json")
arquivo_pendentes = os.path.join(diretorio_atual, "pendentes.json")
arquivo_usuarios = os.path.join(diretorio_atual, "usuarios.json")

# --- LEITURA DO ARQUIVO DE ESTOQUE ---
@st.cache_data
def carregar_estoque():
    itens = []
    caminho_pdf = os.path.join(diretorio_atual, "estoque.pdf")
    
    if os.path.exists(caminho_pdf) and PyPDF2:
        try:
            with open(caminho_pdf, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        for line in text.split('\n'):
                            line = line.strip()
                            # Só adiciona linhas que tenham letras/números (evita espaços em branco do PDF)
                            if len(line) > 2 and re.search(r'[A-Za-z0-9]', line):
                                itens.append(line)
            return sorted(list(set(itens)))
        except Exception as e:
            st.sidebar.error(f"Erro ao ler estoque.pdf: {e}")
            
    return ["Exemplo: Fita Adesiva - Cód 101", "Exemplo: Caixa Parda - Cód 102"] # Padrão caso não ache o PDF

lista_estoque = carregar_estoque()

# --- BANCO DE DADOS DE USUÁRIOS ---
def carregar_usuarios():
    if os.path.exists(arquivo_usuarios):
        try:
            with open(arquivo_usuarios, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {}

def salvar_usuarios(usuarios):
    with open(arquivo_usuarios, "w", encoding="utf-8") as f:
        json.dump(usuarios, f, ensure_ascii=False, indent=4)

# --- CONTROLE DE ACESSO (SESSÃO) ---
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

# --- TELA DE LOGIN ---
if not st.session_state.autenticado:
    col_vazia1, col_login, col_vazia2 = st.columns([1, 2, 1])
    with col_login:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if os.path.exists(caminho_logo):
            st.image(caminho_logo, width=250)
            
        st.title("🔒 Acesso Restrito - LoGuii")
        st.markdown("Faça login ou utilize a chave da União Embalagens para criar uma conta.")
        
        tab_entrar, tab_criar = st.tabs(["Entrar", "Criar Nova Conta"])
        usuarios_db = carregar_usuarios()
        
        with tab_entrar:
            user_login = st.text_input("Usuário")
            pass_login = st.text_input("Senha", type="password")
            if st.button("Entrar no Sistema", type="primary", use_container_width=True):
                if user_login in usuarios_db and usuarios_db[user_login] == pass_login:
                    st.session_state.autenticado = True
                    st.rerun() 
                else:
                    st.error("Usuário ou senha incorretos. Tente novamente.")
                    
        with tab_criar:
            chave_convite = st.text_input("Chave de Convite (Obrigatório)", type="password")
            novo_user = st.text_input("Defina um Nome de Usuário")
            nova_senha = st.text_input("Defina uma Senha", type="password")
            if st.button("Cadastrar Usuário", type="primary", use_container_width=True):
                if chave_convite != "Uniaologuii":
                    st.error("❌ Chave de convite inválida!")
                elif novo_user in usuarios_db:
                    st.error("❌ Esse usuário já existe.")
                elif not novo_user or not nova_senha:
                    st.error("❌ Preencha todos os campos.")
                else:
                    usuarios_db[novo_user] = nova_senha
                    salvar_usuarios(usuarios_db)
                    st.success("✅ Conta criada com sucesso! Volte na aba 'Entrar' para acessar o sistema.")
    st.stop() 


# --- FUNÇÕES DE SALVAMENTO DOS PENDENTES ---
def salvar_pendentes(lista):
    with open(arquivo_pendentes, "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=4)

def carregar_pendentes():
    if os.path.exists(arquivo_pendentes):
        try:
            with open(arquivo_pendentes, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return []

# --- FUNÇÃO DA MARCA D'ÁGUA ---
def aplicar_marca_dagua(image_path):
    if os.path.exists(image_path):
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
        css = f"""
        <style>
        [data-testid="stAppViewContainer"] > .main::before {{
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-image: url("data:image/png;base64,{encoded_string}");
            background-size: 45%; 
            background-position: center;
            background-repeat: no-repeat;
            background-attachment: fixed;
            opacity: 0.10; 
            z-index: -1;
        }}
        </style>
        """
        st.markdown(css, unsafe_allow_html=True)

aplicar_marca_dagua(caminho_caricatura)

# --- CABEÇALHO DA PÁGINA PRINCIPAL ---
col_texto, col_imagem = st.columns([5, 1])
with col_texto:
    st.title("🚚 LoGuii Solução Logística")
    st.markdown("Gerencie pedidos pendentes, adicione itens do estoque e gere rotas otimizadas.")
with col_imagem:
    if os.path.exists(caminho_caricatura):
        st.image(caminho_caricatura, width=130)

if "pendentes" not in st.session_state:
    st.session_state.pendentes = carregar_pendentes()

# --- FUNÇÃO PARA CARREGAR PLANILHA DE CLIENTES ---
@st.cache_data
def carregar_clientes():
    arquivos_possiveis = [
        os.path.join(diretorio_atual, "Listagem_Clientes_de_Franca.xlsx"),
        os.path.join(diretorio_atual, "Listagem_Clientes_de_Franca.xls"),
        os.path.join(diretorio_atual, "clientes.xlsx"),
        "Listagem_Clientes_de_Franca.xlsx" 
    ]
    for arquivo in arquivos_possiveis:
        if os.path.exists(arquivo):
            try:
                df = pd.read_excel(arquivo)
                df.columns = df.columns.str.strip()
                if 'Código' in df.columns: df['Código'] = df['Código'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
                if 'Numero' in df.columns: df['Numero'] = df['Numero'].fillna('').astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
                return df, True, arquivo
            except Exception as e:
                return pd.DataFrame(), False, f"Arquivo encontrado, erro na leitura: {str(e)}"
    return pd.DataFrame(), False, "Planilha não encontrada."

df_clientes, status_ok, msg_erro = carregar_clientes()

# --- FUNÇÃO DO HISTÓRICO ---
def gerenciar_historico(acao='listar', dados=None, idx=None):
    historico = []
    if os.path.exists(arquivo_historico):
        try:
            with open(arquivo_historico, "r", encoding="utf-8") as f:
                historico = json.load(f)
        except: pass
    tempo_atual = time.time()
    historico = [r for r in historico if (tempo_atual - r.get("timestamp", 0)) <= 172800]
    
    if acao == 'adicionar' and dados:
        historico.insert(0, dados)
        with open(arquivo_historico, "w", encoding="utf-8") as f:
            json.dump(historico, f, ensure_ascii=False, indent=4)
    elif acao == 'excluir' and idx is not None:
        if 0 <= idx < len(historico):
            historico.pop(idx)
            with open(arquivo_historico, "w", encoding="utf-8") as f:
                json.dump(historico, f, ensure_ascii=False, indent=4)
    return historico

# --- INTELIGÊNCIA DE ORDENAÇÃO DE URGÊNCIA ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def extrair_minutos(horario_str):
    if not horario_str: return 720
    try:
        numeros = re.findall(r'\d+', str(horario_str))
        if len(numeros) >= 2: return int(numeros[0]) * 60 + int(numeros[1])
        elif len(numeros) == 1:
            n = numeros[0]
            if len(n) >= 3: return int(n[:-2]) * 60 + int(n[-2:])
            return int(n) * 60
    except: pass
    return 720

def otimizar_rota_com_urgencia(origem_lat, origem_lon, pedidos):
    unvisited = pedidos.copy()
    current_lat, current_lon = float(origem_lat), float(origem_lon)
    rota_ordenada = []
    while unvisited:
        best_score = float('inf')
        best_idx = -1
        for i, p in enumerate(unvisited):
            dist = haversine(current_lat, current_lon, float(p['lat']), float(p['lon']))
            bonus = 0
            if p.get('urgente'):
                minutos = extrair_minutos(p.get('horario', ''))
                bonus = 12 + 6 * (1 - (minutos / 1440))
            score = dist - bonus
            if score < best_score:
                best_score = score
                best_idx = i
        next_p = unvisited.pop(best_idx)
        rota_ordenada.append(next_p)
        current_lat = float(next_p['lat'])
        current_lon = float(next_p['lon'])
    return rota_ordenada

# --- MENU LATERAL (SIDEBAR) ---
if os.path.exists(caminho_logo):
    st.sidebar.image(caminho_logo, use_container_width=True)
    st.sidebar.markdown("<br>", unsafe_allow_html=True) 

st.sidebar.header("🔍 1. Adicionar à Fila")
if status_ok and not df_clientes.empty:
    colunas_necessarias = ['Código', 'Cliente', 'Endereco', 'Numero']
    if all(col in df_clientes.columns for col in colunas_necessarias):
        opcoes = df_clientes['Código'] + " - " + df_clientes['Cliente']
        cliente_selecionado = st.sidebar.selectbox("Digite o Código ou Nome do Cliente:", options=["Selecione..."] + opcoes.tolist())
        if st.sidebar.button("➕ Enviar para Pendentes", type="primary"):
            if cliente_selecionado != "Selecione...":
                codigo_busca = cliente_selecionado.split(" - ")[0]
                dados_cli = df_clientes[df_clientes['Código'] == codigo_busca].iloc[0]
                rua_bruta = str(dados_cli['Endereco']).strip()
                rua_limpa = rua_bruta.split('-')[0].strip()
                num = str(dados_cli['Numero']).strip()
                if num.lower() == 'nan': num = ""
                endereco_completo = f"{rua_limpa}, {num}" if num else rua_limpa
                
                st.session_state.pendentes.append({
                    "uid": f"bd_{codigo_busca}_{time.time()}",
                    "cliente": str(dados_cli['Cliente']),
                    "endereco": endereco_completo,
                    "pedido_num": "",
                    "urgente": False,
                    "horario": "",
                    "selecionado": True,
                    "itens": [] # Novo campo para os itens do PDF
                })
                salvar_pendentes(st.session_state.pendentes)
                st.sidebar.success(f"{dados_cli['Cliente']} adicionado à fila!")
            else:
                st.sidebar.warning("Selecione um cliente primeiro.")
else:
    st.sidebar.error("Planilha de clientes não encontrada!")

st.sidebar.divider()

st.sidebar.header("📁 2. Adicionar por Imagem")
modo_imagem = st.sidebar.radio("Como deseja enviar a imagem?", ["Fazer Upload", "Tirar Foto"])
imagens_para_processar = []

if modo_imagem == "Fazer Upload":
    uploaded_files = st.sidebar.file_uploader("Envie a imagem", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    if uploaded_files: imagens_para_processar.extend(uploaded_files)
else:
    foto_camera = st.sidebar.camera_input("📸 Tire a foto")
    if foto_camera: imagens_para_processar.append(foto_camera)

def extrair_dados_imagem(imagem):
    texto = pytesseract.image_to_string(imagem, lang="por")
    texto_cliente = texto
    if "Cliente:" in texto: texto_cliente = texto[texto.find("Cliente:"):]
    elif "CNPJ/CPF:" in texto: texto_cliente = texto[texto.find("CNPJ/CPF:"):]

    cliente_match = re.search(r"Cliente:\s*\d+\s*-\s*(.*?)(?:-|\n)", texto, re.IGNORECASE)
    if not cliente_match: cliente_match = re.search(r"Cliente:\s*(.*)", texto, re.IGNORECASE)
    cliente = cliente_match.group(1).strip() if cliente_match else "Não identificado"

    linha_endereco_match = re.search(r"Endereço:\s*([^\n]*)", texto_cliente, re.IGNORECASE)
    rua, numero = "", ""
    if linha_endereco_match:
        linha = linha_endereco_match.group(1)
        partes = re.split(r'\s*-\s*NULL|\s*N[°ºoOwW]|\s*w[°º]|\s*CEP', linha, flags=re.IGNORECASE)
        rua = partes[0].strip().split('-')[0].strip()
        rua = re.sub(r'[\-,\.\s]+$', '', rua)
        numero_match = re.search(r"(?:N[°ºoOwW\.\*]|\bw[°º]|N\b|- w[°º])\s*(\d+)", linha, re.IGNORECASE)
        if not numero_match: numero_match = re.search(r"(\d+)\s*CEP", linha, re.IGNORECASE)
        numero = numero_match.group(1).strip() if numero_match else ""

    endereco_completo = f"{rua}, {numero}" if (rua and numero) else rua if rua else "Endereço não identificado"
    return {"cliente": cliente, "endereco": endereco_completo, "pedido_num": "", "urgente": False, "horario": "", "selecionado": True, "itens": []}

def geocodificar(endereco):
    url = "https://nominatim.openstreetmap.org/search"
    headers = {'User-Agent': 'LoGuiiApp/1.0'}
    params = {'q': endereco, 'format': 'json', 'limit': 1}
    try:
        res = requests.get(url, headers=headers, params=params)
        dados = res.json()
        if dados: return dados[0]['lat'], dados[0]['lon']
    except: pass
    
    if "," in endereco:
        rua_sem_numero = endereco.split(",")[0].strip()
        if "Franca" not in rua_sem_numero: rua_sem_numero = f"{rua_sem_numero}, Franca, SP, Brasil"
        params = {'q': rua_sem_numero, 'format': 'json', 'limit': 1}
        try:
            res = requests.get(url, headers=headers, params=params)
            dados = res.json()
            if dados: return dados[0]['lat'], dados[0]['lon']
        except: pass
    return None, None

def gerar_pdf(ordem_entregas, nome_motorista):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    largura, altura = A4
    
    if os.path.exists(caminho_logo):
        c.drawImage(caminho_logo, 40, altura - 80, width=120, height=45, preserveAspectRatio=True, mask='auto')
    
    c.setFont("Helvetica-Bold", 16)
    c.drawString(180, altura - 50, "LoGuii Solução Logística")
    
    c.setFont("Helvetica", 10)
    data_atual = datetime.now().strftime("%d/%m/%Y %H:%M")
    c.drawString(180, altura - 65, f"Gerado em: {data_atual}")
    
    if nome_motorista:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(180, altura - 85, f"Motorista: {nome_motorista}")
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, altura - 115, "Ponto de Partida:")
    c.setFont("Helvetica", 12)
    c.drawString(50, altura - 130, "Rua Doutor Ivom Rodrigues Pereira, 5078")
    c.line(50, altura - 145, largura - 50, altura - 145)
    
    y = altura - 175
    for idx, p in enumerate(ordem_entregas):
        if y < 100:
            c.showPage()
            y = altura - 50
            
        prefixo = f"[URGENTE {p.get('horario', '')}] " if p.get('urgente') else ""
        if p.get('urgente'): c.setFillColorRGB(0.8, 0, 0)
            
        c.setFont("Helvetica-Bold", 12)
        num_pedido_str = f" | Pedido: {p['pedido_num']}" if p.get('pedido_num') else ""
        c.drawString(50, y, f"[{idx+1}] {prefixo}Cliente: {p['cliente']}{num_pedido_str}")
        c.setFillColorRGB(0, 0, 0) 
        
        # Checkbox grande de confirmação de entrega do cliente inteiro
        c.rect(largura - 70, y - 10, 15, 15)
        
        y -= 15
        c.setFont("Helvetica", 11)
        c.drawString(50, y, f"Endereço: {p['endereco']}")
        y -= 15
        
        # --- DESENHAR OS ITENS DO ESTOQUE COM CHECKBOXES MENORES ---
        if p.get('itens'):
            y -= 5
            c.setFont("Helvetica-Bold", 10)
            c.drawString(50, y, "Itens a Carregar:")
            y -= 15
            c.setFont("Helvetica", 10)
            for item in p['itens']:
                if y < 50:
                    c.showPage()
                    y = altura - 50
                # Checkbox do item
                c.rect(50, y, 10, 10) 
                # Limita o texto para caber na folha sem cortar
                texto_item = item[:85] + "..." if len(item) > 85 else item
                c.drawString(65, y + 2, texto_item)
                y -= 15
                
        y -= 5
        c.line(50, y, largura - 50, y)
        y -= 25

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "📍 RETORNO: Base União Embalagens")
    y -= 15
    c.setFont("Helvetica", 11)
    c.drawString(50, y, "Endereço: Rua Doutor Ivom Rodrigues Pereira, 5078")
    c.save()
    buffer.seek(0)
    return buffer

if imagens_para_processar:
    for arq_imagem in imagens_para_processar:
        image = Image.open(arq_imagem)
        file_id = getattr(arq_imagem, "name", f"camera_{time.time()}")
        if not any(p.get("uid") == file_id for p in st.session_state.pendentes):
            dados = extrair_dados_imagem(image)
            dados["uid"] = file_id
            st.session_state.pendentes.append(dados)
            salvar_pendentes(st.session_state.pendentes)

# --- BOTÃO DE SAIR NO MENU LATERAL ---
st.sidebar.divider()
if st.sidebar.button("🚪 Sair do Sistema (Logout)"):
    st.session_state.autenticado = False
    st.rerun()

# --- LISTAGEM DE PENDENTES ---
st.subheader("📋 Fila de Pedidos Pendentes")
st.markdown("Marque apenas os que irão nesta viagem. Selecione os itens do estoque e defina urgências.")

st.session_state.pendentes.sort(key=lambda x: not x.get('urgente', False))

if st.session_state.pendentes:
    for i, p in enumerate(st.session_state.pendentes):
        # Linha 1: Dados Principais
        col_sel, col_cli, col_end, col_ped, col_hor, col_bell, col_del = st.columns([0.5, 3, 3, 1.5, 1.5, 0.5, 0.5])
        
        p['selecionado'] = col_sel.checkbox("", value=p.get('selecionado', True), key=f"sel_{p['uid']}")
        p['cliente'] = col_cli.text_input("Cliente:", value=p['cliente'], key=f"cli_{p['uid']}", label_visibility="collapsed")
        p['endereco'] = col_end.text_input("Endereço:", value=p['endereco'], key=f"end_{p['uid']}", label_visibility="collapsed")
        p['pedido_num'] = col_ped.text_input("Pedido:", value=p.get('pedido_num', ''), key=f"ped_{p['uid']}", label_visibility="collapsed")
        
        if p.get('urgente', False):
            p['horario'] = col_hor.text_input("Horário:", value=p.get('horario', ''), key=f"hor_{p['uid']}", placeholder="Ex: 14h00", label_visibility="collapsed")
        else:
            col_hor.write("")

        btn_sino = "🔔" if p.get('urgente', False) else "🔕"
        if col_bell.button(btn_sino, key=f"urg_{p['uid']}", help="Marcar/Desmarcar Urgência"):
            p['urgente'] = not p.get('urgente', False)
            salvar_pendentes(st.session_state.pendentes)
            st.rerun()

        if col_del.button("🗑️", key=f"del_{p['uid']}"):
            st.session_state.pendentes.pop(i)
            salvar_pendentes(st.session_state.pendentes)
            st.rerun()
            
        # Linha 2: Barra de Pesquisa de Itens (Ocupando a largura quase total)
        _, col_itens = st.columns([0.5, 9.5])
        with col_itens:
            # O multiselect permite pesquisar por nome, código ou qualquer palavra solta
            p['itens'] = st.multiselect("📦 Itens do Pedido (Pesquise por nome ou código):", options=lista_estoque, default=p.get('itens', []), key=f"itens_{p['uid']}")

        st.divider()

    if st.button("🗑️ Limpar Toda a Fila de Pendentes"):
        st.session_state.pendentes = []
        salvar_pendentes(st.session_state.pendentes)
        st.rerun()
else:
    st.info("A fila está vazia. Adicione pedidos usando o menu lateral.")

salvar_pendentes(st.session_state.pendentes)

# --- OTIMIZAÇÃO E GERAÇÃO DA ROTA ---
st.subheader("🗺️ Otimização e Impressão")
nome_motorista = st.text_input("👨‍✈️ Nome do Motorista (Opcional - Sairá no PDF):", placeholder="Ex: Roberto")

pedidos_selecionados = [p for p in st.session_state.pendentes if p.get('selecionado', True)]

if st.button("🗺️ Gerar Rota Otimizada", type="primary"):
    if len(pedidos_selecionados) < 1:
        st.warning("Selecione pelo menos um endereço na fila para gerar a rota.")
    else:
        with st.spinner("Analisando distâncias e calculando rotas otimizadas com inteligência de urgência..."):
            origem_texto = "Rua Doutor Ivom Rodrigues Pereira, 5078, Franca, SP, Brasil"
            enderecos_validos = []
            
            lat_o, lon_o = geocodificar(origem_texto)
            if not (lat_o and lon_o):
                st.error("Erro: Não foi possível localizar o endereço de origem padrão.")
                st.stop()
            
            for p in pedidos_selecionados:
                end_completo = f"{p['endereco']}, Franca - SP, Brasil"
                lat, lon = geocodificar(end_completo)
                if lat and lon:
                    p['lat'] = lat
                    p['lon'] = lon
                    enderecos_validos.append(p)
                else:
                    st.warning(f"⚠️ Aviso: O GPS não achou o endereço exato nem a rua próxima de: {p['endereco']}")
                time.sleep(1) 

            if len(enderecos_validos) > 0:
                ordem_entregas = otimizar_rota_com_urgencia(lat_o, lon_o, enderecos_validos)
                st.success("Rota gerada com sucesso! A inteligência do sistema priorizou as entregas urgentes mantendo a melhor eficiência.")
                
                st.subheader("📍 Ordem Sugerida de Entregas")
                for idx, p in enumerate(ordem_entregas):
                    urg_text = f" **[URG. {p.get('horario', '')}]** " if p.get('urgente') else ""
                    num_pedido_tela = f" (Ped: {p['pedido_num']})" if p.get('pedido_num') else ""
                    st.markdown(f"**Parada {idx+1}:** {urg_text}{p['cliente']}{num_pedido_tela} — *{p['endereco']}*")
                
                st.markdown(f"**📍 Retorno:** Base União Embalagens — *Rua Doutor Ivom Rodrigues Pereira, 5078*")
                
                origem_link = "Rua Doutor Ivom Rodrigues Pereira, 5078, Franca, SP".replace(" ", "+")
                destino_final = origem_link 
                pontos_intermediarios = "|".join([f"{p['endereco']}, Franca, SP".replace(" ", "+") for p in ordem_entregas])
                link_maps = f"https://www.google.com/maps/dir/?api=1&origin={origem_link}&destination={destino_final}&waypoints={pontos_intermediarios}"
                    
                st.markdown(f"[🔗 Abrir Rota no Aplicativo do Google Maps]({link_maps})", unsafe_allow_html=True)
                
                st.divider()
                pdf_arquivo = gerar_pdf(ordem_entregas, nome_motorista)
                st.download_button(
                    label="📄 Baixar PDF com Checklist da Rota",
                    data=pdf_arquivo,
                    file_name=f"LoGuii_Rota_{datetime.now().strftime('%d%m%Y_%H%M')}.pdf",
                    mime="application/pdf",
                    type="primary"
                )
                
                st.session_state.pendentes = [p for p in st.session_state.pendentes if not p.get('selecionado', False)]
                salvar_pendentes(st.session_state.pendentes)
                
                nova_rota = {
                    "timestamp": time.time(),
                    "data_formatada": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "motorista": nome_motorista if nome_motorista else "Não informado",
                    "entregas": ordem_entregas,
                    "link_maps": link_maps
                }
                gerenciar_historico(acao='adicionar', dados=nova_rota)
            else:
                st.error("Não foram encontrados endereços válidos suficientes para criar uma rota.")

# --- HISTÓRICO DE ROTAS ---
st.divider()
st.subheader("🕒 Histórico de Rotas (Últimas 48h)")
historico = gerenciar_historico()

if historico:
    for i, rota in enumerate(historico):
        with st.expander(f"🛣️ Rota de {rota['data_formatada']} - Motorista: {rota['motorista']} ({len(rota['entregas'])} entregas)"):
            st.markdown(f"[🔗 Abrir Rota no Google Maps]({rota['link_maps']})", unsafe_allow_html=True)
            for p in rota['entregas']:
                urg = f" **[URG. {p.get('horario', '')}]**" if p.get('urgente') else ""
                num = f" (Ped: {p['pedido_num']})" if p.get('pedido_num') else ""
                st.write(f"-{urg} {p['cliente']}{num}: *{p['endereco']}*")
                
                # Mostra os itens também no histórico na tela
                if p.get('itens'):
                    for item in p['itens']:
                        st.write(f"&nbsp;&nbsp;&nbsp;&nbsp;📦 {item}")
            
            col_b1, col_b2, col_b3 = st.columns([2, 2, 2])
            with col_b1:
                pdf_hist = gerar_pdf(rota['entregas'], rota['motorista'])
                st.download_button(label="📄 Re-imprimir PDF", data=pdf_hist, file_name=f"LoGuii_Hist_{i}.pdf", mime="application/pdf", key=f"dl_hist_{i}")
            
            with col_b2:
                if st.button("✏️ Editar (Devolver p/ Fila)", key=f"edit_hist_{i}", help="Apagará do histórico e devolverá para a fila de pendentes."):
                    for p_hist in rota['entregas']:
                        p_hist['uid'] = f"hist_{time.time()}_{p_hist['cliente']}"
                        p_hist['selecionado'] = True
                        st.session_state.pendentes.append(p_hist)
                    salvar_pendentes(st.session_state.pendentes)
                    gerenciar_historico(acao='excluir', idx=i)
                    st.rerun()
            
            with col_b3:
                if st.button("🗑️ Excluir Rota", key=f"del_hist_{i}", type="secondary"):
                    gerenciar_historico(acao='excluir', idx=i)
                    st.rerun()
else:
    st.info("Nenhuma rota recente salva no histórico ainda.")
